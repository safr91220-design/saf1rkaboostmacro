import ctypes, html, os, threading
from ctypes import wintypes
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QLabel
from . import desktop
from .logger import log

u, k = ctypes.windll.user32, ctypes.windll.kernel32
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
u.SetWindowsHookExW.restype = ctypes.c_void_p
u.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
u.CallNextHookEx.restype = LRESULT
u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
k.GetModuleHandleW.restype = ctypes.c_void_p
k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

class KBD(ctypes.Structure):
    _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

class Hook(threading.Thread):
    """Перехватывает Alt+Tab (только пока Explorer отключён) и передаёт события переключателю."""
    def __init__(self, on_start, on_next, on_commit, on_cancel):
        super().__init__(daemon=True)
        self.cb = (on_start, on_next, on_commit, on_cancel)
        self.active, self.tid, self.hh = False, None, None

    def _proc(self, n, w, l):
        try:
            if n == 0:
                kb = ctypes.cast(l, ctypes.POINTER(KBD)).contents
                if not kb.flags & 0x10:                                   # не трогаем «синтетические» нажатия
                    down, up = w in (0x100, 0x104), w in (0x101, 0x105)
                    if kb.vk == 0x09 and down and kb.flags & 0x20:         # Alt+Tab
                        if not self.active:
                            self.active = True; self.cb[0]()
                        self.cb[1](-1 if u.GetAsyncKeyState(0x10) & 0x8000 else 1)
                        return 1
                    if self.active and kb.vk == 0x1B and down:             # Esc — отмена
                        self.active = False; self.cb[3](); return 1
                    if self.active and up and kb.vk in (0x12, 0xA4, 0xA5): # Alt отпущен — переключаем
                        self.active = False; self.cb[2]()
        except Exception:
            pass
        return u.CallNextHookEx(None, n, w, l)

    def run(self):
        self.tid = k.GetCurrentThreadId()
        self._cb = HOOKPROC(self._proc)
        self.hh = u.SetWindowsHookExW(13, self._cb, k.GetModuleHandleW(None), 0)
        if not self.hh:
            log.warning("Не удалось включить встроенный Alt+Tab"); return
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        u.UnhookWindowsHookEx(self.hh)

    def stop(self):
        if self.tid:
            u.PostThreadMessageW(self.tid, 0x0012, 0, 0)

class Overlay(QLabel):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setStyleSheet("background:#000;color:#fff;border:1px solid #19e6a7;padding:12px;font-family:'Segoe UI';font-size:15px")

    def show_items(self, titles, idx):
        start = max(0, idx - 8)
        rows = []
        for i, t in list(enumerate(titles))[start:start + 9]:
            t = html.escape(t if len(t) < 55 else t[:52] + "…")
            rows.append(f'<span style="background-color:#19e6a7;color:#000000">&nbsp;{t}&nbsp;</span>' if i == idx
                        else f"<span>&nbsp;{t}&nbsp;</span>")
        self.setText("<br>".join(rows)); self.adjustSize()
        g = QApplication.primaryScreen().availableGeometry()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self.show()

class Switcher(QObject):
    """Свой Alt+Tab на время, пока Explorer отключён (штатный переключатель живёт внутри Explorer)."""
    s_start, s_next, s_commit, s_cancel = Signal(), Signal(int), Signal(), Signal()

    def __init__(self):
        super().__init__()
        self.hook, self.wins, self.idx, self.ov = None, [], 0, Overlay()
        self.s_start.connect(self._start); self.s_next.connect(self._next)
        self.s_commit.connect(self._commit); self.s_cancel.connect(self._cancel)
        self.guard = QTimer(self); self.guard.setSingleShot(True); self.guard.timeout.connect(self._cancel)

    def start(self):
        if self.hook:
            return
        self.hook = Hook(self.s_start.emit, self.s_next.emit, self.s_commit.emit, self.s_cancel.emit)
        self.hook.start(); log.info("Встроенный Alt+Tab включён (Explorer отключён)")

    def stop(self):
        if self.hook:
            self.hook.stop(); self.hook = None; self.s_cancel.emit(); log.info("Встроенный Alt+Tab выключен")

    def _start(self):
        self.wins, self.idx = desktop.switch_list({os.getpid()}), 0

    def _next(self, d):
        if len(self.wins) < 2:
            return
        self.idx = (self.idx + d) % len(self.wins)
        self.ov.show_items([t for _, t in self.wins], self.idx); self.guard.start(8000)

    def _commit(self):
        self.ov.hide(); self.guard.stop()
        if 0 < self.idx < len(self.wins):
            desktop.activate(self.wins[self.idx][0])
            log.info("Alt+Tab → %s", self.wins[self.idx][1][:50])

    def _cancel(self):
        self.ov.hide(); self.guard.stop()
