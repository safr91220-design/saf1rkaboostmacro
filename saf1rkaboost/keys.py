"""Таблица клавиш/кнопок мыши и отправка ввода (SendInput). Без внедрения в процессы игры."""
import ctypes
from ctypes import wintypes

MAGIC = 0x53414631     # метка наших синтетических событий (хуки их игнорируют → нет самозапуска)

_SPECIAL = {"SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "BACKSPACE": 0x08, "ESC": 0x1B, "SHIFT": 0x10,
            "CTRL": 0x11, "ALT": 0x12, "CAPSLOCK": 0x14, "PAGEUP": 0x21, "PAGEDOWN": 0x22, "END": 0x23,
            "HOME": 0x24, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28, "INSERT": 0x2D,
            "DELETE": 0x2E, ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
            "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE, "NUMMUL": 0x6A, "NUMADD": 0x6B, "NUMSUB": 0x6D,
            "NUMDOT": 0x6E, "NUMDIV": 0x6F}
KEYS = {c: ("k", ord(c)) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"}
KEYS.update({f"F{i}": ("k", 0x6F + i) for i in range(1, 25)})
KEYS.update({f"NUM{i}": ("k", 0x60 + i) for i in range(10)})
KEYS.update({n: ("k", v) for n, v in _SPECIAL.items()})
MOUSE = {"MOUSE_LEFT": 1, "MOUSE_RIGHT": 2, "MOUSE_MIDDLE": 3, "XBUTTON1": 4, "XBUTTON2": 5}
KEYS.update({n: ("m", v) for n, v in MOUSE.items()})

_VK = {v: n for n, (t, v) in KEYS.items() if t == "k"}
_ALIAS = {0xA0: 0x10, 0xA1: 0x10, 0xA2: 0x11, 0xA3: 0x11, 0xA4: 0x12, 0xA5: 0x12}
EXT = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}
MODS = {"ALT": 1, "CTRL": 2, "SHIFT": 4, "WIN": 8}

def norm_vk(vk): return _ALIAS.get(vk, vk)
def vk_name(vk): return _VK.get(norm_vk(vk))
def is_valid(name): return name in KEYS

def parse_combo(spec):
    """'CTRL+SHIFT+F12' -> (mods, vk) для RegisterHotKey. ValueError при ошибке."""
    parts = [p.strip().upper() for p in str(spec).split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError("нужна комбинация: модификатор + клавиша")
    mods = 0
    for m in parts[:-1]:
        if m not in MODS:
            raise ValueError(f"неизвестный модификатор {m}")
        mods |= MODS[m]
    kind, vk = KEYS.get(parts[-1], (None, None))
    if kind != "k" or parts[-1] in ("CTRL", "ALT", "SHIFT"):
        raise ValueError("последняя клавиша должна быть обычной клавишей")
    return mods, vk

def norm_combo(spec):
    parse_combo(spec)
    parts = [p.strip().upper() for p in str(spec).split("+") if p.strip()]
    mods = [m for m in ("CTRL", "ALT", "SHIFT", "WIN") if m in parts[:-1]]
    return "+".join(mods + [parts[-1]])

class _KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
class _MI(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
class _U(ctypes.Union):
    _fields_ = [("ki", _KI), ("mi", _MI)]
class _IN(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]

_MOUSE_FLAGS = {1: ((0x0002, 0), (0x0004, 0)), 2: ((0x0008, 0), (0x0010, 0)), 3: ((0x0020, 0), (0x0040, 0)),
                4: ((0x0080, 1), (0x0100, 1)), 5: ((0x0080, 2), (0x0100, 2))}
_user32 = None

def send(name, down):
    """Нажатие/отпускание клавиши или кнопки мыши через SendInput (скан-коды). OSError при отказе."""
    global _user32
    if _user32 is None:
        _user32 = ctypes.WinDLL("user32")
    kind, code = KEYS[name]
    if kind == "k":
        flags = 0x0008 | (0x0001 if code in EXT else 0) | (0 if down else 0x0002)
        inp = _IN(1, _U(ki=_KI(0, _user32.MapVirtualKeyW(code, 0), flags, 0, MAGIC)))
    else:
        f, d = _MOUSE_FLAGS[code][0 if down else 1]
        inp = _IN(0, _U(mi=_MI(0, 0, d, f, 0, MAGIC)))
    if _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_IN)) != 1:
        raise OSError("SendInput отклонён (окно запущено от администратора?)")
