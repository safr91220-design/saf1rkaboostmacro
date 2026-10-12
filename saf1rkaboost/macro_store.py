"""Профили и настройки макросов: JSON-файл, проверка данных, импорт/экспорт, конфликты клавиш."""
import copy, json, os
from pathlib import Path
from . import keys
from .config import APP_DIR
from .logger import log

CATS = ["EDIT", "DOUBLE", "SINGLE", "DROP", "SIT", "PICKAXE"]
D_MIN, D_MAX = 0, 1000
TAP_HOLD_MS = 8
FILE = "macros.json"
POINTER = APP_DIR / "macro_location.json"
FORTNITE_EXE = "FortniteClient-Win64-Shipping.exe"
DEFAULT_SETTINGS = {"hotkey_stop": "CTRL+SHIFT+F12", "hotkey_toggle": "CTRL+SHIFT+F11",
                    "block_trigger": True, "engine_on": False, "warn_ack": False}

def _m(select, edit, act, seq, ed=15, kd=10):
    return {"enabled": False, "select": select, "edit": edit, "activate": act,
            "edit_delay": ed, "key_delay": kd, "sequence": seq}

def default_macros():
    # Шаблоны: подберите клавиши и последовательность под свои бинды в игре.
    return {"EDIT": _m("P", "XBUTTON2", "Z", "EDIT, W:EDIT, SELECT"),
            "DOUBLE": _m("P", "XBUTTON2", "X", "EDIT, W:KEY, EDIT, W:EDIT, SELECT"),
            "SINGLE": _m("P", "XBUTTON2", "C", "EDIT, W:EDIT, SELECT, W:KEY, EDIT"),
            "DROP": _m("1", "Q", "V", "SELECT, W:KEY, EDIT"),
            "SIT": _m("F2", "ENTER", "B", "SELECT, W:KEY, EDIT"),
            "PICKAXE": _m("1", "Q", "N", "SELECT, W:KEY")}

def default_profile():
    return {"game_exe": "", "only_in_game": False, "macros": default_macros()}

def default_data():
    fort = default_profile()
    fort.update(game_exe=FORTNITE_EXE, only_in_game=True)
    for c in ("EDIT", "DOUBLE", "SINGLE"):
        fort["macros"][c].update(select="MOUSE_LEFT", edit="G")
    return {"version": 1, "active": "Default", "settings": dict(DEFAULT_SETTINGS),
            "profiles": {"Default": default_profile(), "Fortnite": fort}}

def parse_sequence(text, m):
    """Токены через запятую: SELECT / EDIT / ACTIVATE / KEY:<имя> (нажатие), +X (зажать), -X (отпустить),
    W:EDIT / W:KEY / W:<мс> (пауза). Возвращает [(действие, значение)]. ValueError при ошибке."""
    steps, total = [], 0
    for raw in str(text).split(","):
        t = raw.strip().upper()
        if not t:
            continue
        if t.startswith("W:"):
            a = t[2:]
            try:
                ms = m["edit_delay"] if a == "EDIT" else m["key_delay"] if a == "KEY" else int(a)
            except ValueError:
                raise ValueError(f"неверная пауза «{raw.strip()}»")
            if not D_MIN <= ms <= D_MAX:
                raise ValueError(f"пауза {ms} мс вне диапазона {D_MIN}–{D_MAX}")
            steps.append(("wait", ms)); total += ms
            continue
        mode = "tap"
        if t[0] in "+-":
            mode, t = ("down" if t[0] == "+" else "up"), t[1:]
        role = {"SELECT": m["select"], "EDIT": m["edit"], "ACTIVATE": m["activate"]}
        name = role.get(t) or (t[4:] if t.startswith("KEY:") else None)
        if name is None or not keys.is_valid(name):
            raise ValueError(f"неизвестный шаг «{raw.strip()}»")
        steps.append((mode, name))
    if not steps:
        raise ValueError("последовательность пуста")
    if len(steps) > 32 or total > 5000:
        raise ValueError("слишком длинная последовательность (макс. 32 шага / 5000 мс пауз)")
    return steps

def clean_macro(src, base):
    out = dict(base)
    if not isinstance(src, dict):
        return out
    out["enabled"] = bool(src.get("enabled", False))
    for k in ("select", "edit", "activate"):
        v = str(src.get(k, base[k])).upper()
        out[k] = v if keys.is_valid(v) else base[k]
    if out["activate"] in ("MOUSE_LEFT", "MOUSE_RIGHT"):
        out["activate"] = base["activate"]
    for k in ("edit_delay", "key_delay"):
        try:
            v = int(src.get(k, base[k]))
        except (TypeError, ValueError):
            v = base[k]
        out[k] = max(D_MIN, min(D_MAX, v))
    seq = str(src.get("sequence", base["sequence"]))[:300]
    try:
        parse_sequence(seq, out); out["sequence"] = seq
    except ValueError:
        pass
    return out

def clean_profile(src):
    out = default_profile()
    if not isinstance(src, dict):
        return out
    out["game_exe"] = str(src.get("game_exe", ""))[:260]
    out["only_in_game"] = bool(src.get("only_in_game", False))
    sm = src.get("macros") if isinstance(src.get("macros"), dict) else {}
    base = default_macros()
    out["macros"] = {c: clean_macro(sm.get(c), base[c]) for c in CATS}
    return out

def _clean_data(raw):
    d = default_data()
    if not isinstance(raw, dict):
        return d
    st = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
    for k, dv in DEFAULT_SETTINGS.items():
        x = st.get(k, dv)
        if k.startswith("hotkey_"):
            try:
                x = keys.norm_combo(x)
            except ValueError:
                x = dv
        else:
            x = bool(x)
        d["settings"][k] = x
    profs = raw.get("profiles")
    if isinstance(profs, dict) and profs:
        d["profiles"] = {str(n)[:40]: clean_profile(p) for n, p in list(profs.items())[:30]}
    d["active"] = raw.get("active") if raw.get("active") in d["profiles"] else next(iter(d["profiles"]))
    return d

class Store:
    def __init__(self):
        self.dir = self._dir()
        self.data = self._load()

    @staticmethod
    def _dir():
        try:
            d = Path(json.loads(POINTER.read_text(encoding="utf-8"))["dir"])
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            return APP_DIR

    @property
    def path(self): return self.dir / FILE
    @property
    def settings(self): return self.data["settings"]
    @property
    def active(self): return self.data["active"]
    def names(self): return list(self.data["profiles"])
    def profile(self, name=None): return self.data["profiles"][name or self.active]

    def _load(self):
        try:
            data = _clean_data(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            data = default_data()
        except Exception:
            log.exception("macros.json повреждён — сохраняю копию .bak и беру значения по умолчанию")
            try:
                os.replace(self.path, self.path.with_suffix(".bak"))
            except OSError:
                pass
            data = default_data()
        self.data = data
        self.save()
        return data

    def save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
            return True
        except OSError:
            log.exception("Не удалось сохранить настройки макросов в %s", self.path)
            return False

    def set_macro(self, cat, d):
        self.profile()["macros"][cat] = clean_macro(d, default_macros()[cat]); self.save()
        return self.profile()["macros"][cat]

    def conflicts_for(self, cat, macro=None):
        """[(сообщение, блокирующий?)] — блокирует, если клавиша активации занята ВКЛЮЧЁННЫМ макросом."""
        p = self.profile(); m = macro or p["macros"][cat]; out = []
        for c, o in p["macros"].items():
            if c != cat and o["activate"] == m["activate"]:
                out.append((f"ACTIVATE KEY «{m['activate']}» уже назначена в {c}" + (" (включён)" if o["enabled"] else ""), o["enabled"]))
        if m["activate"] in (m["select"], m["edit"]):
            out.append(("ACTIVATE совпадает с SELECT/EDIT этого макроса", False))
        return out

    # --- профили ---
    def _unique(self, base):
        n = (base.strip() or "Profile")[:40]; name, i = n, 2
        while name in self.data["profiles"]:
            name, i = f"{n} ({i})", i + 1
        return name

    def new(self, name):
        n = self._unique(name); self.data["profiles"][n] = default_profile(); self.data["active"] = n; self.save(); return n

    def copy(self):
        n = self._unique(self.active + " copy")
        self.data["profiles"][n] = copy.deepcopy(self.profile()); self.data["active"] = n; self.save(); return n

    def rename(self, new):
        new, old = new.strip()[:40], self.active
        if not new or (new in self.data["profiles"] and new != old):
            raise ValueError("имя пустое или уже занято")
        self.data["profiles"] = {(new if n == old else n): p for n, p in self.data["profiles"].items()}
        self.data["active"] = new; self.save()

    def delete(self):
        if len(self.data["profiles"]) < 2:
            raise ValueError("нельзя удалить последний профиль")
        del self.data["profiles"][self.active]; self.data["active"] = self.names()[0]; self.save()

    def set_active(self, name):
        if name in self.data["profiles"]:
            self.data["active"] = name; self.save()

    def export_profile(self, path):
        Path(path).write_text(json.dumps({"format": "saf1rkaboost-profile", "version": 1, "name": self.active,
                                          "profile": self.profile()}, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_profile(self, path):
        p = Path(path)
        if p.stat().st_size > 1_000_000:
            raise ValueError("файл слишком большой")
        raw = json.loads(p.read_text(encoding="utf-8"))
        prof = raw.get("profile", raw) if isinstance(raw, dict) else None
        if not isinstance(prof, dict) or "macros" not in prof:
            raise ValueError("это не профиль saf1rkaboost")
        n = self._unique(str(raw.get("name", "Imported")) if isinstance(raw, dict) else "Imported")
        self.data["profiles"][n] = clean_profile(prof); self.data["active"] = n; self.save(); return n

    def reset_all(self):
        self.data = default_data(); self.save()

    def move_to(self, folder):
        d = Path(folder); d.mkdir(parents=True, exist_ok=True)
        (d / ".write_test").write_text("ok"); (d / ".write_test").unlink()
        self.dir = d; self.save()
        POINTER.write_text(json.dumps({"dir": str(d)}), encoding="utf-8")
