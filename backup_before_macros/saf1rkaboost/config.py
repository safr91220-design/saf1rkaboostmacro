import json, os
from pathlib import Path

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "saf1rkaboost"
APP_DIR.mkdir(parents=True, exist_ok=True)
CFG_FILE = APP_DIR / "config.json"

DEFAULTS = {
    "auto_detect": True, "ask_on_game": True, "auto_enable": False,
    "minimize_windows": True, "hide_taskbar": True, "hide_desktop_icons": True,
    "raise_game_priority": True, "games": [], "suspend_on_boost": [],
}

class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        try:
            self.data.update(json.loads(CFG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass

    def __getitem__(self, k):
        return self.data[k]

    def set(self, k, v):
        self.data[k] = v
        try:
            CFG_FILE.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
