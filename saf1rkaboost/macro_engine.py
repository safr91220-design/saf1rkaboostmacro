"""Движок макросов: перехват только ваших нажатий (LL-хуки) + отправка ввода через SendInput.
Никакого внедрения в процессы игр. Включённые макросы реагируют на клавишу ACTIVATE."""
import atexit, ctypes, queue, threading, time
from ctypes import wintypes
import psutil
from . import keys, macro_store as ms
from .logger import log

MIN_GAP = 0.12      # защита от повторного запуска (сек)
MAX_RUN = 5.0       # аварийный потолок длительности макроса (сек)
_A = None
_BTN = {1: "MOUSE_LEFT", 2: "MOUSE_RIGHT", 3: "MOUSE_MIDDLE", 4: "XBUTTON1", 5: "XBUTTON2"}

class _KBD(ctypes.Structure):
    _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
class _MSL(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG), ("data", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

def _api():
    global _A
    if _A is None:
        u, k = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")
        hp = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        u.SetWindowsHookExW.restype = ctypes.c_void_p
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, hp, ctypes.c_void_p, wintypes.DWORD]
        u.CallNextHookEx.restype = ctypes.c_ssize_t
        u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        k.GetModuleHandleW.restype = ctypes.c_void_p
        k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        _A = (u, k, hp)
    return _A

class _Hook(threading.Thread):
    def __init__(self, owner, mouse):
        super().__init__(daemon=True)
        self.o, self.mouse, self.tid, self.hh = owner, mouse, None, []

    def _key(self, n, w, l):
        try:
            if n == 0:
                kb = ctypes.cast(l, ctypes.POINTER(_KBD)).contents
                if kb.extra != keys.MAGIC:
                    name = keys.vk_name(kb.vk)
                    if name and self.o._input(name, w in (0x100, 0x104)):
                        return 1
        except Exception:
            pass
        return _api()[0].CallNextHookEx(None, n, w, l)

    def _mouse(self, n, w, l):
        try:
            if n == 0 and w != 0x200:
                m = ctypes.cast(l, ctypes.POINTER(_MSL)).contents
                if m.extra != keys.MAGIC:
                    b = {0x201: (1, 1), 0x202: (1, 0), 0x204: (2, 1), 0x205: (2, 0), 0x207: (3, 1), 0x208: (3, 0)}.get(w)
                    if w in (0x20B, 0x20C):
                        b = (4 if (m.data >> 16) == 1 else 5, 1 if w == 0x20B else 0)
                    if b and self.o._input(_BTN[b[0]], bool(b[1])):
                        return 1
        except Exception:
            pass
        return _api()[0].CallNextHookEx(None, n, w, l)

    def run(self):
        u, k, hp = _api()
        self.tid = k.GetCurrentThreadId()
        self._kp, self._mp = hp(self._key), hp(self._mouse)
        hm = k.GetModuleHandleW(None)
        self.hh.append(u.SetWindowsHookExW(13, self._kp, hm, 0))
        if self.mouse:
            self.hh.append(u.SetWindowsHookExW(14, self._mp, hm, 0))
        if not all(self.hh):
            log.warning("Не удалось установить перехват клавиш/мыши для макросов")
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        for h in self.hh:
            if h:
                u.UnhookWindowsHookEx(h)

    def stop(self):
        if self.tid:
            ctypes.WinDLL("user32").PostThreadMessageW(self.tid, 0x0012, 0, 0)

class MacroEngine:
    def __init__(self, store):
        self.store, self.master, self.send = store, False, keys.send   # send можно подменить (тесты)
        self.running = None
        self._quit, self._stop = threading.Event(), threading.Event()
        self._q = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._held, self._down, self._swallowed = set(), set(), set()
        self._map, self._block, self._only, self._game, self._fg = {}, True, False, "", ""
        self._hook = self._worker = self._poller = None
        self._last_end, self._err_logged = 0.0, False
        atexit.register(self._release_all)

    # ---------- конфигурация ----------
    def reload(self):
        p, s = self.store.profile(), self.store.settings
        m = {mc["activate"]: c for c, mc in p["macros"].items() if mc["enabled"]}
        self._block = bool(s.get("block_trigger", True))
        self._game, self._only = p["game_exe"].strip().lower(), bool(p["only_in_game"] and p["game_exe"].strip())
        self._map = m
        if self.master and m:
            self._start_worker()
            need_mouse = any(keys.KEYS[n][0] == "m" for n in m)
            if self._only and not (self._poller and self._poller.is_alive()):
                self._poller = threading.Thread(target=self._poll_fg, daemon=True); self._poller.start()
            if not (self._hook and self._hook.is_alive() and self._hook.mouse == need_mouse):
                self._stop_hook()
                self._hook = _Hook(self, need_mouse); self._hook.start()
                log.info("Макросы активны: %s", ", ".join(f"{c}={k}" for k, c in m.items()))
        else:
            self._stop_hook()
            self.stop_all()

    def set_master(self, on):
        self.master = bool(on)
        log.info("Движок макросов: %s", "ON" if on else "OFF")
        self.reload()

    def _start_worker(self):
        self._quit.clear()
        if not (self._worker and self._worker.is_alive()):
            self._worker = threading.Thread(target=self._work, daemon=True); self._worker.start()

    def _stop_hook(self):
        h, self._hook = self._hook, None
        if h:
            h.stop(); h.join(1.0)
        self._down.clear(); self._swallowed.clear()

    def shutdown(self):
        self.master = False
        self._stop_hook(); self.stop_all(); self._quit.set()

    # ---------- обработка ввода (поток хука, должна быть быстрой) ----------
    def _allowed(self):
        return not self._only or self._fg == self._game

    def _input(self, name, down):
        cat = self._map.get(name)
        if cat is None:
            return False
        if down:
            if name in self._down:                       # автоповтор удерживаемой клавиши
                return name in self._swallowed
            self._down.add(name)
            if not self._allowed():
                return False
            self._trigger(cat)
            if self._block:
                self._swallowed.add(name); return True
            return False
        self._down.discard(name)
        if name in self._swallowed:
            self._swallowed.discard(name); return True
        return False

    def _trigger(self, cat):
        if self.running or time.monotonic() - self._last_end < MIN_GAP:
            return                                       # защита от повторного запуска
        try:
            self._q.put_nowait(cat)
        except queue.Full:
            pass

    def _poll_fg(self):
        u = _api()[0]
        while not self._quit.wait(0.3) and self.master:
            if not self._only:
                continue
            try:
                pid = wintypes.DWORD()
                u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
                self._fg = psutil.Process(pid.value).name().lower()
            except Exception:
                self._fg = ""

    # ---------- выполнение ----------
    def _work(self):
        while not self._quit.is_set():
            try:
                cat = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            self._run(cat)

    def _emit(self, name, down):
        try:
            self.send(name, down)
        except Exception as e:
            if not self._err_logged:
                log.error("Ввод не отправлен: %s", e); self._err_logged = True
            raise RuntimeError(str(e))
        with self._lock:
            (self._held.add if down else self._held.discard)(name)

    def _run(self, cat):
        try:
            mc = dict(self.store.profile()["macros"][cat])
            steps = ms.parse_sequence(mc["sequence"], mc)
        except Exception as e:
            log.warning("Макрос %s не запущен: %s", cat, e); return
        self._stop.clear(); self.running = cat
        t0 = time.monotonic(); done = True
        try:
            for kind, val in steps:
                if self._stop.is_set() or time.monotonic() - t0 > MAX_RUN:
                    done = False; break
                if kind == "wait":
                    if val and self._stop.wait(val / 1000):
                        done = False; break
                elif kind == "tap":
                    self._emit(val, True)
                    try:
                        self._stop.wait(ms.TAP_HOLD_MS / 1000)
                    finally:
                        self._emit(val, False)
                else:
                    self._emit(val, kind == "down")
        except RuntimeError:
            done = False
        finally:
            self._release_all()
            self.running, self._last_end = None, time.monotonic()
        log.info("Макрос %s %s за %d мс", cat, "выполнен" if done else "остановлен", (time.monotonic() - t0) * 1000)

    def stop_all(self):
        """Немедленная остановка: прерывает паузы, очищает очередь, отпускает все зажатые клавиши."""
        self._stop.set()
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        self._release_all()

    def _release_all(self):
        with self._lock:
            held, _ = list(self._held), self._held.clear()
        for n in held:
            try:
                self.send(n, False)
            except Exception:
                pass
