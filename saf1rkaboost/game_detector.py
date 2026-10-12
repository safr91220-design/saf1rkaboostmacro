import os
from dataclasses import dataclass
import psutil
from . import desktop

NOT_GAMES = {"explorer.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe", "vlc.exe",
             "powerpnt.exe", "code.exe", "python.exe", "pythonw.exe", "saf1rkaboost.exe", "applicationframehost.exe",
             "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe", "mpc-hc64.exe"}
SYSROOT = os.environ.get("SystemRoot", r"C:\Windows").lower()

@dataclass
class Game:
    pid: int
    name: str
    exe: str
    source: str
    proc: psutil.Process

class GameDetector:
    def __init__(self, cfg):
        self.cfg = cfg

    def find(self):
        manual = {os.path.basename(g).lower() for g in self.cfg["games"]}
        if manual:
            for p in psutil.process_iter(["name", "exe"]):
                n = (p.info["name"] or "").lower()
                if n in manual:
                    return Game(p.pid, n, p.info["exe"] or n, "вручную", p)
        if self.cfg["auto_detect"]:
            pid = desktop.foreground_fullscreen_pid()
            if pid and pid != os.getpid():
                try:
                    p = psutil.Process(pid)
                    n, exe = p.name().lower(), (p.exe() if True else "")
                except psutil.Error:
                    return None
                if n not in NOT_GAMES and not exe.lower().startswith(SYSROOT):
                    return Game(pid, n, exe, "авто (полноэкранное окно)", p)
        return None
