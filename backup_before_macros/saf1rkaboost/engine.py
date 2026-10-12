import os
import threading
import psutil
from . import processes as P, shell
from .desktop import DesktopMode
from .logger import log

class BoostEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.desktop = DesktopMode()
        self.enabled = False
        self.game = None
        self.suspended = {}      # pid -> (name, create_time)
        self.old_priority = {}   # pid -> priority class
        self._ram_before = 0
        self.shell_suspended = False
        self._hk = None
        self.switcher = None
        self.before = (0, 0, 0)

    def keep(self):
        return {os.getpid()} | ({self.game.pid} if self.game else set())

    def attach_game(self, game):
        self.game = game
        if self.enabled:
            self._raise_priority()

    def enable(self):
        if self.enabled:
            return
        try:
            self._ram_before = psutil.virtual_memory().used
            self._log_before()
            c = self.cfg
            self.desktop.enable(c["minimize_windows"], c["hide_taskbar"], c["hide_desktop_icons"], self.keep())
            self._raise_priority()
            for name in c["suspend_on_boost"]:
                for p in psutil.process_iter(["name"]):
                    if (p.info["name"] or "").lower() == name.lower():
                        self.suspend(p.pid)
            self.enabled = True
            log.info("Performance Mode: ON")
        except Exception:
            log.exception("Ошибка включения Gaming Mode, откатываю изменения")
            self.disable()

    def disable(self, restore_shell=True):
        try:
            if restore_shell:
                self.shell_restore()
            self.resume_all()
            for pid, prio in list(self.old_priority.items()):
                try:
                    psutil.Process(pid).nice(prio)
                except psutil.Error:
                    pass
            self.old_priority.clear()
            self.desktop.restore()
            if self.enabled:
                diff = (self._ram_before - psutil.virtual_memory().used) / 2**20
                log.info("Performance Mode: OFF. Изменение занятой RAM: %+.0f МБ. FPS смотрите в Optimization Log", -diff)
        except Exception:
            log.exception("Ошибка при восстановлении")
        finally:
            self.enabled = False

    def _raise_priority(self):
        if not (self.game and self.cfg["raise_game_priority"]) or self.game.pid in self.old_priority:
            return
        try:
            p = psutil.Process(self.game.pid)
            self.old_priority[p.pid] = p.nice()
            p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
            log.info("Приоритет %s: Above Normal", self.game.name)
        except psutil.Error as e:
            self.old_priority.pop(self.game.pid, None)
            log.warning("Не удалось поднять приоритет игры: %s", e)

    def suspend(self, pid):
        r = P.protection_reason(pid, self.keep())
        if r:
            log.warning("PID %s не приостановлен: %s", pid, r)
            return False
        try:
            p = psutil.Process(pid)
            p.suspend()
            self.suspended[pid] = (p.name(), p.create_time())
            log.info("Приостановлен: %s (PID %s)", p.name(), pid)
            return True
        except psutil.Error as e:
            log.warning("Не удалось приостановить PID %s: %s", pid, e)
            return False

    def resume_all(self):
        for pid, (name, ct) in list(self.suspended.items()):
            try:
                p = psutil.Process(pid)
                if abs(p.create_time() - ct) < 1:
                    p.resume()
                    log.info("Возобновлён: %s (PID %s)", name, pid)
            except psutil.NoSuchProcess:
                pass
            except Exception:
                log.exception("Не удалось возобновить %s", name)
        self.suspended.clear()

    def close(self, pid, name=""):
        try:
            P.terminate(pid, self.keep())
            log.info("Закрыт: %s (PID %s). Восстановить закрытый процесс нельзя.", name, pid)
            return True
        except Exception as e:
            log.warning("Не закрыт %s (PID %s): %s", name, pid, e)
            return False

    # ---------- Full Desktop Suspend (Explorer) ----------
    def shell_suspend(self):
        if self.shell_suspended:
            return True
        if shell.suspend():
            self.shell_suspended = True
            self._hk = shell.Hotkey(self.disable)
            self._hk.start()
            if self.switcher:
                self.switcher.start()
            return True
        return False

    def shell_restore(self):
        try:
            if self._hk:
                self._hk.stop(); self._hk = None
            if self.switcher:
                self.switcher.stop()
            if self.shell_suspended or shell.state() == "SUSPENDED":
                shell.restore()
            self.shell_suspended = False
        except Exception:
            log.exception("Не удалось восстановить Explorer")

    def shell_watch(self):
        """Если Explorer вернулся сам (Windows/пользователь) — не воюем с ним, просто обновляем статус."""
        if self.shell_suspended and shell.state() == "RUNNING":
            log.info("Explorer снова запущен (Windows или пользователем)")
            if self.switcher:
                self.switcher.stop()
            self.shell_suspended = False
            if self._hk:
                self._hk.stop(); self._hk = None
            shell.FLAG.unlink(missing_ok=True)

    # ---------- метрики до/после (FPS автоматически не измеряется) ----------
    @staticmethod
    def _snap():
        return psutil.cpu_percent(None), psutil.virtual_memory().used / 2**20, len(psutil.pids())

    def _log_before(self):
        self.before = self._snap()
        log.info("До оптимизации: CPU %.0f%%, RAM %.0f МБ, процессов %d", *self.before)
        t = threading.Timer(8.0, self._log_after)
        t.daemon = True
        t.start()

    def _log_after(self):
        if not self.enabled:
            return
        c, r, n = self._snap()
        c0, r0, n0 = self.before
        log.info("Через 8 с: CPU %.0f%% (%+.0f), RAM %.0f МБ (%+.0f), процессов %d (%+d). "
                 "FPS замерьте сами и впишите ниже", c, c - c0, r, r - r0, n, n - n0)
