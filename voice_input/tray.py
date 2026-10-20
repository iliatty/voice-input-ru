"""Иконка в системном трее Windows."""
from __future__ import annotations

import logging
from typing import Callable

from .paths import resource_path

log = logging.getLogger(__name__)


class TrayController:
    """Небольшая обёртка над pystray, не зависящая от Tk."""

    def __init__(self) -> None:
        self._icon = None
        self.available = False

    def start(
        self,
        on_show: Callable[[], None],
        on_record: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> bool:
        try:
            import pystray
            from PIL import Image

            icon_path = resource_path("assets/icon-64.png")
            image = Image.open(str(icon_path)).convert("RGBA")
            menu = pystray.Menu(
                pystray.MenuItem(
                    "Открыть",
                    lambda _icon, _item: on_show(),
                    default=True,
                ),
                pystray.MenuItem(
                    "Записать / остановить",
                    lambda _icon, _item: on_record(),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Выход",
                    lambda _icon, _item: on_exit(),
                ),
            )
            self._icon = pystray.Icon(
                "VoiceInputRU",
                image,
                "Голосовой ввод",
                menu,
            )
            self._icon.run_detached()
            self.available = True
            log.info("Иконка трея запущена")
            return True
        except Exception:
            log.exception("Не удалось запустить иконку трея")
            self._icon = None
            self.available = False
            return False

    def notify(self, message: str, title: str = "Голосовой ввод") -> None:
        if not self._icon:
            return
        try:
            self._icon.notify(message, title)
        except Exception:
            log.debug("Не удалось показать уведомление трея", exc_info=True)

    def stop(self) -> None:
        if not self._icon:
            return
        try:
            self._icon.stop()
        except Exception:
            log.debug("Не удалось остановить иконку трея", exc_info=True)
        finally:
            self._icon = None
            self.available = False
