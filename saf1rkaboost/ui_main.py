"""Главное окно: боковая панель FPS BOOST / MACROS (+ SETTINGS внизу), единый тёмно-фиолетовый стиль."""
import psutil
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget)
from . import autostart, keys, monitor, shell
from .config import Config
from .engine import BoostEngine
from .game_detector import GameDetector
from .logger import callback_handler, log
from .macro_engine import MacroEngine
from .macro_store import Store
from .switcher import Switcher
from .ui import LogBridge
from .ui_macros import MacrosPage
from .widgets import STYLE, FadeStack, KeyField, Toggle, hline, make_row

HK_DEFAULT = {"stop": "CTRL+SHIFT+F12", "toggle": "CTRL+SHIFT+F11", "restore": "CTRL+ALT+SHIFT+R"}
HK_LABEL = {"stop": "STOP ALL MACROS", "toggle": "MACRO ENGINE ON/OFF", "restore": "EMERGENCY RESTORE DESKTOP"}
WARN_BOOST = ("Во время отключения Explorer исчезнут панель задач, рабочий стол и Проводник.\n\n"
              "Игра продолжит работать. Alt+Tab работает через встроенный переключатель "
              "(окна из трея в нём не видны — откройте нужные заранее).\n"
              "Вернуть всё: RESTORE DESKTOP, выход из игры, закрытие программы или аварийная горячая клавиша.\n\n"
              "Прирост FPS не гарантирован — проверяйте замерами. Продолжить?")
WARN_MACRO = ("Макросы отправляют нажатия клавиш за вас. Многие игры (в том числе Fortnite с Easy Anti-Cheat) "
              "могут считать это нарушением правил и блокировать аккаунт. Программа не обходит античит и "
              "не внедряется в игру — вы используете её на свой риск и сами отвечаете за соблюдение правил игры.\n\n"
              "Включить движок макросов?")

def section(text):
    l = QLabel(text); l.setObjectName("section"); return l

def reset_btn(fn):
    b = QPushButton("RESET"); b.setObjectName("reset"); b.clicked.connect(fn); return b

class FpsPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s, self._n = s, 0
        cfg = s.cfg
        left = QVBoxLayout(); left.setSpacing(12)
        t = QLabel("FPS BOOST"); t.setObjectName("h1"); sub = QLabel("DESKTOP SHELL SUSPEND · PERFORMANCE MODE"); sub.setObjectName("note")
        self.btn_boost = QPushButton("ENABLE BOOST"); self.btn_boost.setObjectName("big"); self.btn_boost.clicked.connect(lambda: self.start_boost())
        self.btn_restore = QPushButton("RESTORE DESKTOP"); self.btn_restore.clicked.connect(self.restore)
        self.status = QLabel(); self.status.setStyleSheet("font-weight:700;font-size:14px")
        self.auto = Toggle(cfg["auto_boost"]); self.auto.toggled.connect(self._auto)
        self.hk = KeyField("combo"); self.hk.set(cfg["restore_hotkey"]); self.hk.changed.connect(lambda v: s.try_set_hk("restore", v))
        for w in (t, sub, hline(), self.btn_boost, self.btn_restore, self.status):
            left.addWidget(w)
        left.addWidget(make_row("AUTO MODE", self.auto)); 
        note = QLabel("AUTO MODE: при запуске игры из списка справа Boost включается сам, после выхода из игры всё восстанавливается.")
        note.setObjectName("note"); note.setWordWrap(True); left.addWidget(note)
        left.addWidget(make_row("EMERGENCY KEY", self.hk, lambda: s.try_set_hk("restore", HK_DEFAULT["restore"])))
        left.addStretch(1)
        right = QVBoxLayout(); right.setSpacing(8)
        right.addWidget(section("MONITOR"))
        self.bars = {}
        for n in ("CPU", "RAM", "GPU"):
            row = QHBoxLayout(); b = QProgressBar(); b.setRange(0, 100); b.setTextVisible(False)
            val = QLabel("—"); val.setFixedWidth(130); lab = QLabel(n); lab.setFixedWidth(36)
            row.addWidget(lab); row.addWidget(b, 1); row.addWidget(val); right.addLayout(row); self.bars[n] = (b, val)
        right.addWidget(section("GAMES (AUTO MODE / DETECTION)"))
        self.games = QListWidget(); self.games.setMaximumHeight(90); self.games.addItems(cfg["games"]); right.addWidget(self.games)
        gb = QHBoxLayout()
        for text, fn in (("ADD EXE", self.add_game), ("REMOVE", self.del_game)):
            b = QPushButton(text); b.clicked.connect(fn); gb.addWidget(b)
        gb.addStretch(1); right.addLayout(gb)
        right.addWidget(section("ACTION LOG"))
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True); self.log_view.setPlainText("\n".join(s.history))
        right.addWidget(self.log_view, 1)
        h = QHBoxLayout(self); h.setContentsMargins(26, 20, 26, 16); h.setSpacing(28)
        lw = QWidget(); lw.setLayout(left); lw.setFixedWidth(340); h.addWidget(lw); h.addLayout(right, 1)
        self.refresh()

    def _auto(self, on):
        self.s.cfg.set("auto_boost", on); log.info("AUTO MODE: %s", "ON" if on else "OFF")

    def add_game(self):
        f, _ = QFileDialog.getOpenFileName(self, "EXE игры", "", "Executable (*.exe)")
        if f and f not in self.s.cfg["games"]:
            self.s.cfg.set("games", self.s.cfg["games"] + [f]); self.games.addItem(f)

    def del_game(self):
        r = self.games.currentRow()
        if r >= 0:
            g = list(self.s.cfg["games"]); g.pop(r); self.s.cfg.set("games", g); self.games.takeItem(r)

    def start_boost(self, confirm=True):
        e = self.s.engine
        if confirm and QMessageBox.warning(self, "saf1rka_boost", WARN_BOOST, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                           QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        e.enable()
        if not e.shell_suspend():
            log.warning("Explorer не отключён — подробности выше в журнале")
        self.refresh()

    def restore(self):
        self.s.engine.disable(); self.refresh()

    def refresh(self):
        e = self.s.engine
        sus = e.shell_suspended or shell.state() == "SUSPENDED"
        self.status.setText("●  DESKTOP SUSPENDED" if sus else "●  DESKTOP ACTIVE")
        self.status.setStyleSheet("font-weight:700;font-size:14px;color:%s" % ("#ff5c6c" if sus else "#9b30ff"))
        self.btn_boost.setText("BOOST ACTIVE" if e.enabled or sus else "ENABLE BOOST")
        self.btn_boost.setEnabled(not (e.enabled or sus)); self.btn_restore.setEnabled(e.enabled or sus)

    def tick(self):
        e = self.s.engine
        e.shell_watch(); self.refresh()
        c, (pct, used, total), g = monitor.cpu(), monitor.ram(), self.s.gpu.value
        for n, v, text in (("CPU", c, f"{c:.0f}%"), ("RAM", pct, f"{used:.1f} / {total:.1f} GB"),
                           ("GPU", g or 0, f"{g:.0f}%" if g is not None else "n/a (NVIDIA only)")):
            self.bars[n][0].setValue(int(v)); self.bars[n][1].setText(text)
        self._n += 1
        if self._n % 2 == 0:
            self._check_game()

    def _check_game(self):
        e, s = self.s.engine, self.s
        g = e.game
        if g:
            try:
                alive = g.proc.is_running()
            except psutil.Error:
                alive = False
            if not alive:
                log.info("Игра закрыта: %s — восстанавливаю всё", g.name)
                e.game = None
                if e.enabled or e.shell_suspended:
                    e.disable()
                self.refresh()
            return
        f = s.detector.find()
        if not f:
            return
        e.attach_game(f); log.info("Обнаружена игра: %s (%s)", f.name, f.source)
        if s.cfg["auto_boost"] and f.source == "вручную" and not (e.enabled or e.shell_suspended):
            log.info("AUTO MODE: включаю Boost для %s", f.name); self.start_boost(confirm=False)

class SettingsPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s, self.fields = s, {}
        v = QVBoxLayout(self); v.setContentsMargins(26, 20, 26, 16); v.setSpacing(10)
        t = QLabel("SETTINGS"); t.setObjectName("h1"); v.addWidget(t); v.addWidget(hline())
        v.addWidget(section("GLOBAL HOTKEYS"))
        for k in ("stop", "toggle", "restore"):
            f = KeyField("combo"); f.set(s.get_hk(k)); f.changed.connect(lambda val, k=k: s.try_set_hk(k, val)); self.fields[k] = f
            v.addWidget(make_row(HK_LABEL[k], f, lambda _=False, k=k: s.try_set_hk(k, HK_DEFAULT[k])))
        v.addWidget(section("MACROS"))
        from PySide6.QtWidgets import QComboBox
        self.combo = QComboBox(); self.combo.setMinimumWidth(200); self.combo.currentTextChanged.connect(s.set_profile)
        v.addWidget(make_row("PROFILE", self.combo))
        blk = Toggle(s.store.settings["block_trigger"]); blk.toggled.connect(self._block)
        v.addWidget(make_row("BLOCK ACTIVATE KEY", blk))
        v.addWidget(section("FPS BOOST OPTIONS"))
        for key, label in (("minimize_windows", "MINIMIZE WINDOWS"), ("hide_taskbar", "HIDE TASKBAR (PERF. MODE)"),
                           ("hide_desktop_icons", "HIDE DESKTOP ICONS"), ("raise_game_priority", "RAISE GAME PRIORITY"),
                           ("auto_detect", "DETECT FULLSCREEN GAMES")):
            tg = Toggle(s.cfg[key]); tg.toggled.connect(lambda on, k=key: s.cfg.set(k, on)); v.addWidget(make_row(label, tg))
        v.addWidget(section("APPLICATION"))
        try:
            on = autostart.is_enabled()
        except Exception:
            on = False
        self.auto = Toggle(on); self.auto.toggled.connect(self._autostart); v.addWidget(make_row("START WITH WINDOWS", self.auto))
        self.folder = QLabel(str(s.store.dir)); self.folder.setObjectName("note")
        ch = QPushButton("CHANGE…"); ch.clicked.connect(self._folder)
        fr = QHBoxLayout(); fr.addWidget(self.folder, 1); fr.addWidget(ch)
        fw = QWidget(); fw.setLayout(fr); v.addWidget(make_row("CONFIG FOLDER", fw, expand=True))
        b = QHBoxLayout()
        d = QPushButton("RESTORE DEFAULT SETTINGS"); d.clicked.connect(self._defaults)
        e = QPushButton("EXPORT LOGS"); e.clicked.connect(self._export)
        b.addWidget(d); b.addWidget(e); b.addStretch(1); v.addLayout(b); v.addStretch(1)
        self.refresh()

    def refresh(self):
        for k, f in self.fields.items():
            f.set(self.s.get_hk(k))
        self.combo.blockSignals(True); self.combo.clear(); self.combo.addItems(self.s.store.names())
        self.combo.setCurrentText(self.s.store.active); self.combo.blockSignals(False)
        self.folder.setText(str(self.s.store.dir))

    def _block(self, on):
        self.s.store.settings["block_trigger"] = on; self.s.store.save(); self.s.apply_macros()

    def _autostart(self, on):
        try:
            autostart.set_enabled(on); log.info("Автозапуск с Windows: %s", "ВКЛ" if on else "выкл")
        except Exception as e:
            log.warning("Автозапуск не изменён: %s", e); self.auto.setChecked(not on)
            QMessageBox.warning(self, "saf1rka_boost", f"Не удалось изменить автозапуск:\n{e}")

    def _folder(self):
        d = QFileDialog.getExistingDirectory(self, "Папка конфигураций", str(self.s.store.dir))
        if d:
            try:
                self.s.store.move_to(d); log.info("Папка конфигураций: %s", d); self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "saf1rka_boost", f"Папка недоступна для записи:\n{e}")

    def _defaults(self):
        if QMessageBox.question(self, "saf1rka_boost", "Сбросить ВСЕ профили макросов и горячие клавиши к значениям по умолчанию?") \
                == QMessageBox.StandardButton.Yes:
            self.s.restore_defaults()

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export logs", "saf1rkaboost_log.txt", "Text (*.txt)")
        if p:
            try:
                open(p, "w", encoding="utf-8").write("\n".join(self.s.history) + "\n"); log.info("Журнал экспортирован: %s", p)
            except OSError as e:
                QMessageBox.warning(self, "saf1rka_boost", f"Экспорт не удался:\n{e}")

class MainShell(QMainWindow):
    sig_toggle = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("saf1rka_boost"); self.resize(1060, 650); self.setMinimumSize(920, 580); self.setStyleSheet(STYLE)
        self.cfg, self.history, self._hk, self._down = Config(), [], [], False
        self.engine = BoostEngine(self.cfg); self.detector = GameDetector(self.cfg)
        self.switcher = Switcher(); self.engine.switcher = self.switcher
        self.store = Store(); self.macro = MacroEngine(self.store)
        self.bridge = LogBridge(); self.bridge.message.connect(self._on_log)
        callback_handler.callbacks.append(self.bridge.message.emit)
        self.gpu = monitor.GpuPoller(); self.gpu.start(); monitor.cpu()

        self.fps = FpsPage(self)
        self.macros = MacrosPage(self.store, self.apply_macros, self.set_master)
        self.settings = SettingsPage(self)
        self.macros.profile_changed.connect(self.settings.refresh)
        self.stack = FadeStack()
        for p in (self.fps, self.macros, self.settings):
            self.stack.addWidget(p)

        side = QFrame(); side.setObjectName("side"); side.setFixedWidth(190)
        sv = QVBoxLayout(side); sv.setContentsMargins(0, 18, 0, 14); sv.setSpacing(2)
        brand = QLabel("saf1rka_<span style='color:#9b30ff'>boost</span>"); brand.setObjectName("brand"); brand.setContentsMargins(18, 0, 0, 18)
        sv.addWidget(brand)
        self.grp = QButtonGroup(self)
        for i, name in enumerate(("FPS BOOST", "MACROS")):
            b = QPushButton(name); b.setObjectName("nav"); b.setCheckable(True); b.setChecked(i == 0); self.grp.addButton(b, i); sv.addWidget(b)
        sv.addStretch(1)
        sb = QPushButton("SETTINGS"); sb.setObjectName("nav"); sb.setCheckable(True); self.grp.addButton(sb, 2); sv.addWidget(sb)
        self.grp.idClicked.connect(self.stack.fade_to)
        central = QWidget(); h = QHBoxLayout(central); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
        h.addWidget(side); h.addWidget(self.stack, 1); self.setCentralWidget(central)

        self.sig_toggle.connect(self.toggle_master)
        self.apply_hotkeys()
        if self.store.settings["engine_on"] and self.store.settings["warn_ack"]:
            self.macro.set_master(True)
        elif self.store.settings["engine_on"]:
            self.store.settings["engine_on"] = False; self.macros.engine_toggle.setChecked(False)
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(1000)
        log.info("saf1rka_boost запущен")

    # ---------- журнал ----------
    def _on_log(self, msg):
        self.history.append(msg); del self.history[:-500]
        self.fps.log_view.appendPlainText(msg)

    def _tick(self):
        try:
            self.fps.tick()
        except Exception:
            log.exception("Ошибка цикла мониторинга")

    # ---------- макросы ----------
    def apply_macros(self):
        self.macro.reload()

    def set_master(self, on):
        if on and not self.store.settings["warn_ack"]:
            B = QMessageBox.StandardButton
            if QMessageBox.warning(self, "saf1rka_boost", WARN_MACRO, B.Yes | B.No, B.No) != B.Yes:
                return False
            self.store.settings["warn_ack"] = True
        self.store.settings["engine_on"] = on; self.store.save(); self.macro.set_master(on)
        return True

    def toggle_master(self):
        on = not self.store.settings["engine_on"]
        if self.set_master(on):
            self.macros.engine_toggle.setChecked(on)

    def set_profile(self, name):
        if name and name != self.store.active:
            self.store.set_active(name); log.info("Профиль: %s", name); self.macros.refresh(); self.macro.reload()

    # ---------- горячие клавиши ----------
    def get_hk(self, k):
        return self.cfg["restore_hotkey"] if k == "restore" else self.store.settings["hotkey_" + k]

    def try_set_hk(self, k, spec):
        try:
            v = keys.norm_combo(spec)
        except ValueError as e:
            log.warning("Горячая клавиша не принята: %s", e); self._sync_hk(); return
        if any(v == self.get_hk(o) for o in HK_DEFAULT if o != k):
            log.warning("Горячая клавиша %s уже назначена на другое действие", v); self._sync_hk(); return
        if k == "restore":
            self.engine.set_hotkey(v)
        else:
            self.store.settings["hotkey_" + k] = v; self.store.save(); self.apply_hotkeys()
        log.info("Горячая клавиша «%s»: %s", HK_LABEL[k], v); self._sync_hk()

    def _sync_hk(self):
        self.fps.hk.set(self.get_hk("restore")); self.settings.refresh()

    def apply_hotkeys(self):
        for h in self._hk:
            h.stop(); h.join(0.5)
        self._hk = []
        for k, cb in (("stop", self.macro.stop_all), ("toggle", self.sig_toggle.emit)):
            h = shell.Hotkey(cb, self.store.settings["hotkey_" + k], HK_LABEL[k]); h.start(); self._hk.append(h)

    def restore_defaults(self):
        self.macro.set_master(False); self.store.reset_all()
        self.cfg.set("restore_hotkey", HK_DEFAULT["restore"]); self.cfg.set("auto_boost", False)
        self.fps.auto.setChecked(False); self.macros.engine_toggle.setChecked(False)
        self.macros.refresh(); self.settings.refresh(); self._sync_hk(); self.apply_hotkeys()
        log.info("Настройки сброшены к значениям по умолчанию")

    # ---------- завершение ----------
    def shutdown(self):
        if getattr(self, "_down", False):
            return
        self._down = True
        self.timer.stop()
        for h in self._hk:
            h.stop()
        self.macro.shutdown(); self.gpu.stop(); self.engine.disable()

    def closeEvent(self, e):
        self.shutdown(); log.info("saf1rka_boost закрыт"); e.accept()
