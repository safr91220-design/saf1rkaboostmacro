import ctypes, getpass, os, subprocess, sys, threading, time
from ctypes import wintypes
import psutil
from .config import APP_DIR
from .logger import log

SYSROOT = os.environ.get("SystemRoot", r"C:\Windows")
EXPLORER = os.path.join(SYSROOT, "explorer.exe")
FLAG = APP_DIR / "shell_suspended.flag"   # существует, пока Explorer отключён нами
u = ctypes.windll.user32
u.FindWindowW.restype = wintypes.HWND
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

def state():
    return "RUNNING" if u.FindWindowW("Shell_TrayWnd", None) else "SUSPENDED"

def _procs():
    me, out = getpass.getuser().lower(), []
    for p in psutil.process_iter(["name", "exe", "username"]):
        i = p.info
        if ((i["name"] or "").lower() == "explorer.exe" and (i["exe"] or "").lower() == EXPLORER.lower()
                and (i["username"] or "").split("\\")[-1].lower() == me):
            out.append(p)
    return out

def suspend():
    """Завершает только explorer.exe текущего пользователя. Без циклов перезапуска."""
    procs = _procs()
    if not procs:
        log.warning("Explorer не запущен — нечего отключать"); return False
    FLAG.write_text(str(os.getpid()))
    _start_watchdog()
    h = u.FindWindowW("Shell_TrayWnd", None)
    if h:
        u.PostMessageW(h, 0x5B4, 0, 0)          # штатный «Exit Explorer» (без автоперезапуска)
    alive = psutil.wait_procs(procs, timeout=3)[1]
    for p in alive:
        try: p.terminate()
        except psutil.Error: pass
    for p in psutil.wait_procs(alive, timeout=3)[1]:
        try: p.kill()
        except psutil.Error: pass
    time.sleep(2)
    if _procs():
        log.error("Windows сам перезапустил Explorer — оболочка не отключена (повторных попыток нет)")
        FLAG.unlink(missing_ok=True); return False
    log.info("Explorer отключён (SUSPENDED). Аварийно: Ctrl+Alt+Shift+R")
    return True

def restore():
    """Запускает explorer.exe, если оболочки нет. Максимум 2 попытки."""
    if state() == "RUNNING":
        FLAG.unlink(missing_ok=True); return True
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            log.warning("Программа запущена от администратора — Explorer тоже будет с повышенными правами")
    except Exception:
        pass
    for _ in range(2):
        if not _procs():
            subprocess.Popen([EXPLORER], close_fds=True, creationflags=0x00000008)
        for _ in range(20):
            time.sleep(0.5)
            if state() == "RUNNING":
                break
        if state() == "RUNNING":
            break
    ok = state() == "RUNNING"
    FLAG.unlink(missing_ok=True)
    if ok:
        log.info("Explorer восстановлен (RUNNING)")
    else:
        log.error("Не удалось запустить Explorer. Ctrl+Shift+Esc → Запустить новую задачу → explorer.exe")
    return ok

def _start_watchdog():
    """Отдельный процесс: если программа внезапно завершится, он вернёт Explorer."""
    try:
        cmd = [sys.executable, "--watchdog", str(os.getpid())] if getattr(sys, "frozen", False) else \
              [sys.executable, os.path.abspath(sys.argv[0]), "--watchdog", str(os.getpid())]
        subprocess.Popen(cmd, close_fds=True, creationflags=0x00000208,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        log.exception("Не удалось запустить процесс аварийного восстановления")

def watchdog(parent_pid):
    try:
        parent = psutil.Process(parent_pid)
    except psutil.Error:
        parent = None
    while FLAG.exists():
        time.sleep(1)
        if parent is None or not parent.is_running():
            log.warning("Основная программа завершилась — восстанавливаю Explorer")
            restore(); return

class Hotkey(threading.Thread):
    """Глобальное аварийное сочетание Ctrl+Alt+Shift+R."""
    def __init__(self, callback):
        super().__init__(daemon=True)
        self.cb, self.tid = callback, None

    def run(self):
        self.tid = ctypes.windll.kernel32.GetCurrentThreadId()
        if not u.RegisterHotKey(None, 1, 0x0001 | 0x0002 | 0x0004 | 0x4000, 0x52):
            log.warning("Не удалось зарегистрировать Ctrl+Alt+Shift+R"); return
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:
                log.warning("Аварийное восстановление (Ctrl+Alt+Shift+R)")
                try: self.cb()
                except Exception: log.exception("Ошибка аварийного восстановления")
        u.UnregisterHotKey(None, 1)

    def stop(self):
        if self.tid:
            u.PostThreadMessageW(self.tid, 0x0012, 0, 0)
