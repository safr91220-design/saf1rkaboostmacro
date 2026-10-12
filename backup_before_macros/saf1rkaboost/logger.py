import logging
from logging.handlers import RotatingFileHandler
from .config import APP_DIR

log = logging.getLogger("saf1rkaboost")

class CallbackHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.callbacks = []

    def emit(self, record):
        msg = self.format(record)
        for cb in list(self.callbacks):
            try:
                cb(msg)
            except Exception:
                pass

callback_handler = CallbackHandler()

def setup():
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%d.%m %H:%M:%S")
    fh = RotatingFileHandler(APP_DIR / "saf1rkaboost.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    for h in (fh, callback_handler):
        h.setFormatter(fmt)
        log.addHandler(h)
