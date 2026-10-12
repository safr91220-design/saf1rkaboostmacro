import ctypes
from ctypes import wintypes
from .logger import log

u = ctypes.windll.user32
H, I, S = wintypes.HWND, ctypes.c_int, wintypes.LPCWSTR
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
u.FindWindowW.restype = H;   u.FindWindowW.argtypes = [S, S]
u.FindWindowExW.restype = H; u.FindWindowExW.argtypes = [H, H, S, S]
u.GetWindow.restype = H;     u.GetWindow.argtypes = [H, wintypes.UINT]
u.GetForegroundWindow.restype = H
u.ShowWindow.argtypes = [H, I]
for f in (u.IsWindowVisible, u.IsIconic, u.IsWindow, u.GetWindowTextLengthW):
    f.argtypes = [H]
u.GetWindowLongW.argtypes = [H, I]
u.GetClassNameW.argtypes = [H, wintypes.LPWSTR, I]
u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
u.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
u.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]

SW_HIDE, SW_MINIMIZE, SW_RESTORE, SW_SHOW = 0, 6, 9, 5
SKIP_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}

def _cls(h):
    b = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, b, 256)
    return b.value

def _pid(h):
    p = wintypes.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value

def _cloaked(h):
    try:
        v = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(v), 4)
        return bool(v.value)
    except Exception:
        return False

def visible_windows(exclude_pids, minimized=False):
    out = []
    def cb(h, _):
        if (u.IsWindowVisible(h) and (minimized or not u.IsIconic(h)) and not u.GetWindow(h, 4)
                and not (u.GetWindowLongW(h, -20) & 0x80) and u.GetWindowTextLengthW(h) > 0
                and _cls(h) not in SKIP_CLASSES and _pid(h) not in exclude_pids and not _cloaked(h)):
            out.append(h)
        return True
    u.EnumWindows(WNDENUMPROC(cb), 0)
    return out

def foreground_fullscreen_pid():
    h = u.GetForegroundWindow()
    if not h or _cls(h) in SKIP_CLASSES:
        return None
    r = wintypes.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    if (r.right - r.left >= u.GetSystemMetrics(0) and r.bottom - r.top >= u.GetSystemMetrics(1)):
        return _pid(h)
    return None

def _taskbars():
    res, h = [], u.FindWindowW("Shell_TrayWnd", None)
    if h:
        res.append(h)
    h = None
    while True:
        h = u.FindWindowExW(None, h, "Shell_SecondaryTrayWnd", None)
        if not h:
            return res
        res.append(h)

def _icons_view():
    dv = u.FindWindowExW(u.FindWindowW("Progman", None), None, "SHELLDLL_DefView", None)
    w = None
    while not dv:
        w = u.FindWindowExW(None, w, "WorkerW", None)
        if not w:
            return None
        dv = u.FindWindowExW(w, None, "SHELLDLL_DefView", None)
    return u.FindWindowExW(dv, None, "SysListView32", None)

class DesktopMode:
    """Explorer.exe НЕ завершается: только сворачиваем окна и прячем панель/значки."""
    def __init__(self):
        self.minimized, self.taskbars, self.icons = [], [], None

    def enable(self, minimize, taskbar, icons, keep_pids):
        if minimize:
            for h in visible_windows(keep_pids):
                u.ShowWindow(h, SW_MINIMIZE)
                self.minimized.append(h)
            log.info("Свернуто окон: %d", len(self.minimized))
        if taskbar:
            self.taskbars = [h for h in _taskbars() if u.IsWindowVisible(h)]
            for h in self.taskbars:
                u.ShowWindow(h, SW_HIDE)
            log.info("Панель задач скрыта (Alt+Tab работает)")
        if icons:
            lv = _icons_view()
            if lv and u.IsWindowVisible(lv):
                u.ShowWindow(lv, SW_HIDE)
                self.icons = lv
                log.info("Значки рабочего стола скрыты")

    def restore(self):
        for h in self.taskbars:
            u.ShowWindow(h, SW_SHOW)
        if self.icons:
            u.ShowWindow(self.icons, SW_SHOW)
        for h in reversed(self.minimized):
            if u.IsWindow(h):
                u.ShowWindow(h, SW_RESTORE)
        if self.minimized or self.taskbars or self.icons:
            log.info("Рабочий стол восстановлен")
        self.minimized, self.taskbars, self.icons = [], [], None

def force_restore():
    """Аварийное восстановление: python main.py --restore"""
    for h in _taskbars():
        u.ShowWindow(h, SW_SHOW)
    lv = _icons_view()
    if lv:
        u.ShowWindow(lv, SW_SHOW)

u.SetForegroundWindow.argtypes = [H]
u.BringWindowToTop.argtypes = [H]
u.GetWindowTextW.argtypes = [H, wintypes.LPWSTR, I]

def _title(h):
    b = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(h, b, 256)
    return b.value

def switch_list(exclude_pids):
    """Окна для Alt+Tab (включая свёрнутые), сверху — самое «свежее»."""
    return [(h, _title(h)) for h in visible_windows(exclude_pids, minimized=True)]

def activate(h):
    if u.IsIconic(h):
        u.ShowWindow(h, SW_RESTORE)
    k32 = ctypes.windll.kernel32
    fg = u.GetForegroundWindow()
    me = k32.GetCurrentThreadId()
    other = u.GetWindowThreadProcessId(fg, None) if fg else 0
    if other and other != me:
        u.AttachThreadInput(me, other, True)
    u.SetForegroundWindow(h); u.BringWindowToTop(h)
    if other and other != me:
        u.AttachThreadInput(me, other, False)
    if u.GetForegroundWindow() != h:          # запасной способ
        u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)
        u.SetForegroundWindow(h)
