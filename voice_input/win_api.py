"""Небольшая обёртка над Win32 API для фокуса, окон и DPI."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
import time

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_RESTORE = 9

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

MONITOR_DEFAULTTONEAREST = 2


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wt.LONG),
        ("top", wt.LONG),
        ("right", wt.LONG),
        ("bottom", wt.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wt.DWORD),
    ]


def enable_dpi_awareness() -> None:
    """Должно вызываться до создания Tk-окон."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def set_app_user_model_id(app_id: str = "VoiceInputRU") -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def top_level_hwnd(widget) -> int:
    """Настоящий HWND окна Tk (winfo_id() — это дочерний TkChild)."""
    hwnd = int(widget.winfo_id())
    parent = user32.GetParent(hwnd)
    return int(parent) if parent else hwnd


def _top_level_hwnd(root) -> int:
    return top_level_hwnd(root)


def set_dark_title_bar(root) -> None:
    try:
        hwnd = _top_level_hwnd(root)
        value = ctypes.c_int(1)
        applied = False
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
            result = dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                applied = True
                break
        if not applied:
            # Запасной вариант для старых сборок Windows 10.
            ctypes.windll.uxtheme.SetWindowTheme(hwnd, "DarkMode_Explorer", None)
        # Цвет заголовка и текста в Windows 11 (мягко игнорируем ошибки).
        color = ctypes.c_int(0x0015100E)  # BGR для #0E1015
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))
        text_color = ctypes.c_int(0x00F9F5F3)
        dwmapi.DwmSetWindowAttribute(
            hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color)
        )
        log.debug("Тёмный заголовок: hwnd=%s applied=%s", hwnd, applied)
    except Exception as exc:
        log.debug("Не удалось включить тёмный заголовок: %s", exc)


def get_foreground_window() -> int:
    try:
        return int(user32.GetForegroundWindow())
    except Exception:
        return 0


def get_window_title(hwnd: int) -> str:
    if not hwnd:
        return ""
    try:
        length = int(user32.GetWindowTextLengthW(hwnd))
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value.strip()
    except Exception:
        return ""


def get_window_pid(hwnd: int) -> int:
    if not hwnd:
        return 0
    try:
        pid = wt.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def is_window(hwnd: int) -> bool:
    try:
        return bool(hwnd) and bool(user32.IsWindow(hwnd))
    except Exception:
        return False


def is_own_window(hwnd: int) -> bool:
    pid = get_window_pid(hwnd)
    return bool(pid) and pid == os.getpid()


def is_minimized(hwnd: int) -> bool:
    try:
        return bool(user32.IsIconic(hwnd))
    except Exception:
        return False


def show_no_activate(hwnd: int) -> None:
    try:
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
    except Exception as exc:
        log.debug("show_no_activate: %s", exc)


def set_topmost(hwnd: int) -> None:
    try:
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
    except Exception:
        pass


def cursor_workarea() -> tuple[int, int, int, int]:
    """Рабочая область монитора под курсором: left, top, right, bottom."""
    try:
        point = wt.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
            return int(work.left), int(work.top), int(work.right), int(work.bottom)
    except Exception as exc:
        log.debug("cursor_workarea: %s", exc)
    return 0, 0, int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def overlay_position(width: int, height: int, margin: int = 28) -> tuple[int, int]:
    left, top, right, bottom = cursor_workarea()
    x = left + max(0, (right - left - width) // 2)
    y = bottom - height - margin
    if y < top:
        y = top + margin
    return x, y


def focus_window(hwnd: int, delay: float = 0.06) -> bool:
    """Возвращает фокус внешнему окну, обходя ограничение foreground lock."""
    if not is_window(hwnd):
        return False
    if get_foreground_window() == hwnd:
        return True
    try:
        if is_minimized(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.12)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        if user32.SetForegroundWindow(hwnd):
            time.sleep(delay)
            if get_foreground_window() == hwnd:
                return True

        foreground = get_foreground_window()
        current_thread = int(kernel32.GetCurrentThreadId())
        foreground_thread = (
            int(user32.GetWindowThreadProcessId(foreground, None)) if foreground else 0
        )
        target_thread = int(user32.GetWindowThreadProcessId(hwnd, None))
        attached: list[int] = []
        for thread_id in (foreground_thread, target_thread):
            if thread_id and thread_id != current_thread and thread_id not in attached:
                if user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            for thread_id in attached:
                user32.AttachThreadInput(current_thread, thread_id, False)
        time.sleep(delay)
        return get_foreground_window() == hwnd
    except Exception as exc:
        log.warning("Не удалось вернуть фокус окну %s: %s", hwnd, exc)
        return False


def flash_window(hwnd: int) -> None:
    try:
        user32.FlashWindow(hwnd, True)
    except Exception:
        pass
