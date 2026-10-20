"""Запись с микрофона и потоковое распознавание Vosk."""
from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import dataclass
from typing import Callable

import numpy as np
import sounddevice as sd
import vosk

log = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    hostapi: str

    @property
    def key(self) -> str:
        return f"{self.name}|{self.hostapi}"

    @property
    def label(self) -> str:
        return f"{self.name}  ·  {self.hostapi}"


def list_input_devices() -> list[AudioDevice]:
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception as exc:
        log.error("Не удалось получить список аудиоустройств: %s", exc)
        return []

    result: list[AudioDevice] = []
    seen: set[tuple[str, str]] = set()
    for index, device in enumerate(devices):
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        name = str(device.get("name", "")).strip()
        try:
            hostapi = str(hostapis[int(device.get("hostapi", 0))]["name"])
        except (IndexError, KeyError, TypeError, ValueError):
            hostapi = "Аудио"
        dedupe_key = (name, hostapi)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(AudioDevice(index=index, name=name, hostapi=hostapi))
    return result


def default_input_device() -> AudioDevice | None:
    try:
        index = sd.default.device[0]
        if index is None or int(index) < 0:
            return None
        device = sd.query_devices(int(index))
        if int(device.get("max_input_channels", 0)) <= 0:
            return None
        hostapis = sd.query_hostapis()
        hostapi = str(hostapis[int(device["hostapi"])]["name"])
        return AudioDevice(int(index), str(device["name"]), hostapi)
    except Exception:
        return None


def resolve_device(key: str) -> AudioDevice | None:
    devices = list_input_devices()
    if not key:
        return default_input_device() or (devices[0] if devices else None)
    for device in devices:
        if device.key == key:
            return device
    # Старый/неточный ключ: ищем хотя бы по имени.
    name = key.split("|", 1)[0]
    for device in devices:
        if device.name == name:
            return device
    return default_input_device() or (devices[0] if devices else None)


def _pick_samplerate(device_index: int) -> int:
    try:
        sd.check_input_settings(
            device=device_index,
            channels=1,
            dtype="int16",
            samplerate=TARGET_SAMPLE_RATE,
        )
        return TARGET_SAMPLE_RATE
    except Exception:
        pass
    info = sd.query_devices(device_index)
    try:
        rate = int(round(float(info.get("default_samplerate", 48000))))
    except (TypeError, ValueError):
        rate = 48000
    if rate <= 0:
        rate = 48000
    sd.check_input_settings(device=device_index, channels=1, dtype="int16", samplerate=rate)
    return rate


class _StreamingResampler:
    """Линейный ресемплер с переносом последнего отсчёта между блоками."""

    def __init__(self, source_rate: int, target_rate: int = TARGET_SAMPLE_RATE) -> None:
        self.source_rate = source_rate
        self.target_rate = target_rate
        self.ratio = source_rate / target_rate
        self._last: int | None = None

    def process(self, samples: np.ndarray) -> np.ndarray:
        if self.source_rate == self.target_rate or samples.size == 0:
            return samples
        data = samples.astype(np.float32)
        if self._last is not None:
            data = np.concatenate((np.array([self._last], dtype=np.float32), data))
        count = int(len(data) / self.ratio)
        if count <= 0:
            self._last = int(data[-1])
            return np.empty(0, dtype=np.int16)
        positions = np.arange(count, dtype=np.float64) * self.ratio
        resampled = np.interp(positions, np.arange(len(data)), data)
        self._last = int(data[-1])
        return np.clip(resampled, -32768, 32767).astype(np.int16)


class Recorder:
    """Одна сессия записи: поток -> Vosk -> partial/final."""

    def __init__(
        self,
        model: vosk.Model,
        *,
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
        on_level: Callable[[float], None],
        on_error: Callable[[str], None],
    ) -> None:
        self.model = model
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_level = on_level
        self.on_error = on_error
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stream: sd.InputStream | None = None
        self._running = False
        self._discard = False
        self._samplerate = TARGET_SAMPLE_RATE
        self._last_partial = ""
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def samplerate(self) -> int:
        return self._samplerate

    def start(self, device_key: str = "") -> bool:
        if self._running:
            return True
        device = resolve_device(device_key)
        if device is None:
            self.on_error("Не найдено устройство ввода. Подключите микрофон и обновите список.")
            return False
        try:
            samplerate = _pick_samplerate(device.index)
        except Exception as exc:
            log.exception("Не удалось открыть микрофон")
            self.on_error(
                f"Не удалось открыть микрофон «{device.name}».\n"
                f"Проверьте, что он не занят другим приложением.\n\n{exc}"
            )
            return False

        self._samplerate = samplerate
        self._discard = False
        self._last_partial = ""
        self._queue = queue.Queue()
        self._running = True

        def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
            if status:
                log.debug("Аудиопоток: %s", status)
            try:
                self._queue.put(("audio", bytes(indata)))
            except Exception:
                pass

        try:
            stream = sd.InputStream(
                device=device.index,
                channels=1,
                samplerate=samplerate,
                dtype="int16",
                blocksize=max(400, int(samplerate * 0.1)),
                callback=callback,
            )
            stream.start()
        except Exception as exc:
            self._running = False
            log.exception("Ошибка запуска аудиопотока")
            self.on_error(
                "Не удалось начать запись с микрофона.\n"
                "Выберите другое устройство ввода в настройках.\n\n"
                f"{exc}"
            )
            return False

        self._stream = stream
        self._thread = threading.Thread(
            target=self._worker,
            name="voice-recognizer",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "Запись начата: %s (%s Гц) -> Vosk %s Гц",
            device.label,
            samplerate,
            TARGET_SAMPLE_RATE,
        )
        return True

    def _worker(self) -> None:
        recognizer = vosk.KaldiRecognizer(self.model, TARGET_SAMPLE_RATE)
        parts: list[str] = []
        resampler = _StreamingResampler(self._samplerate)
        try:
            while True:
                kind, payload = self._queue.get()
                if kind == "stop":
                    break
                if kind != "audio":
                    continue
                samples = np.frombuffer(payload, dtype=np.int16)  # type: ignore[arg-type]
                if samples.size:
                    rms = float(np.sqrt(np.mean((samples.astype(np.float32) / 32768.0) ** 2)))
                    self.on_level(min(1.0, rms * 10.0))

                samples = resampler.process(samples)
                if samples.size == 0:
                    continue
                if recognizer.AcceptWaveform(samples.tobytes()):
                    segment = str(json.loads(recognizer.Result()).get("text", "")).strip()
                    if segment:
                        parts.append(segment)
                partial = str(
                    json.loads(recognizer.PartialResult()).get("partial", "")
                ).strip()
                combined = " ".join(parts + ([partial] if partial else [])).strip()
                if combined != self._last_partial:
                    self._last_partial = combined
                    self.on_partial(combined)

            final = str(json.loads(recognizer.FinalResult()).get("text", "")).strip()
            if final:
                parts.append(final)
            text = " ".join(parts).strip()
            if self._discard:
                log.info("Распознавание отменено пользователем")
            else:
                self.on_final(text)
        except Exception as exc:
            log.exception("Ошибка распознавания")
            if not self._discard:
                self.on_error(f"Ошибка распознавания речи:\n{exc}")
        finally:
            self._running = False

    def stop(self) -> None:
        """Останавливает поток; итог придёт в on_final асинхронно."""
        if not self._running and self._stream is None:
            return
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception as exc:
                log.debug("stream.stop: %s", exc)
            try:
                stream.close()
            except Exception as exc:
                log.debug("stream.close: %s", exc)
        self._queue.put(("stop", None))

    def cancel(self) -> None:
        self._discard = True
        self.stop()
        log.info("Запись отменена")

    def wait(self, timeout: float = 3.0) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
