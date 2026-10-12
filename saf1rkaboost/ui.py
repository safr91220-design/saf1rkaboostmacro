import psutil
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)
from . import monitor, processes as P, shell
from .config import Config
from .engine import BoostEngine
from .game_detector import GameDetector
from .logger import callback_handler, log
from .switcher import Switcher

STYLE = """
QWidget{background:#0e1117;color:#e6e9ef;font-family:'Segoe UI';font-size:13px}
QTabWidget::pane{border:1px solid #1f2430}
QTabBar::tab{background:#141821;padding:10px 22px;border:none}
QTabBar::tab:selected{background:#1b2130;color:#19e6a7}
QPushButton{background:#1b2130;border:1px solid #2a3142;border-radius:8px;padding:8px 16px}
QPushButton:hover{border-color:#19e6a7}
QPushButton:disabled{color:#5b6372}
QPushButton#boost{font-size:34px;font-weight:800;border:4px solid #19e6a7;border-radius:100px;background:#10261f;color:#19e6a7}
QPushButton#boost:hover{background:#17382d}
QProgressBar{background:#1b2130;border:none;border-radius:6px;max-height:12px}
QProgressBar::chunk{background:#19e6a7;border-radius:6px}
QTableWidget,QListWidget,QPlainTextEdit{background:#141821;border:1px solid #1f2430;gridline-color:#1f2430}
QHeaderView::section{background:#1b2130;border:none;padding:6px}
"""

class LogBridge(QObject):
    message = Signal(str)

class Meter(QWidget):
    def __init__(self, title):
        super().__init__()
        l = QHBoxLayout(self)
        t = QLabel(title); t.setFixedWidth(45)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setTextVisible(False)
        self.v = QLabel("—"); self.v.setFixedWidth(170)
        for w in (t, self.bar, self.v):
            l.addWidget(w)

    def set(self, pct, text):
        self.bar.setValue(int(pct)); self.v.setText(text)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("saf1rkaboost"); self.resize(900, 650); self.setStyleSheet(STYLE)
        self.cfg = Config(); self.engine = BoostEngine(self.cfg); self.detector = GameDetector(self.cfg)
        self.switcher = Switcher(); self.engine.switcher = self.switcher
        self._prompted, self._n = None, 0
        monitor.cpu(); P.snapshot()  # «прогрев» счётчиков CPU
        tabs = QTabWidget()
        for w, n in ((self._dash(), "Главная"), (self._procs(), "Процессы"),
                     (self._settings(), "Настройки"), (self._logtab(), "Лог")):
            tabs.addTab(w, n)
        self.setCentralWidget(tabs)
        self.bridge = LogBridge(); self.bridge.message.connect(self.log_view.appendPlainText)
        callback_handler.callbacks.append(self.bridge.message.emit)
        self.gpu = monitor.GpuPoller(); self.gpu.start()
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(1000)
        self._state(); log.info("saf1rkaboost запущен")

    # ---------- вкладки ----------
    def _dash(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.status = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.game_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.boost = QPushButton("BOOST"); self.boost.setObjectName("boost"); self.boost.setFixedSize(200, 200)
        self.boost.clicked.connect(self.enable_mode)
        self.restore_btn = QPushButton("RESTORE DESKTOP"); self.restore_btn.clicked.connect(self.disable_mode)
        self.shell_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.shell_btn = QPushButton("Full Desktop Suspend: ENABLE"); self.shell_btn.clicked.connect(self.suspend_shell)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(self.boost); row.addStretch()
        self.m_cpu, self.m_ram, self.m_gpu = Meter("CPU"), Meter("RAM"), Meter("GPU")
        note = QLabel("Gaming Mode освобождает ресурсы, но прирост FPS не гарантирован.\n"
                      "Проверяйте замерами (CapFrameX / PresentMon / MSI Afterburner).")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter); note.setStyleSheet("color:#7b8496")
        for x in (self.status, self.game_lbl):
            v.addWidget(x)
        v.addLayout(row); v.addWidget(self.restore_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.shell_btn, alignment=Qt.AlignmentFlag.AlignCenter); v.addWidget(self.shell_lbl)
        for m in (self.m_cpu, self.m_ram, self.m_gpu):
            v.addWidget(m)
        v.addWidget(note); return w

    def _procs(self):
        w = QWidget(); v = QVBoxLayout(w); top = QHBoxLayout()
        self.sort = QComboBox(); self.sort.addItems(["cpu", "ram"])
        for text, fn in (("Обновить", self.refresh_procs), ("Закрыть выбранные", self.close_sel),
                         ("Приостановить выбранные", self.suspend_sel), ("Возобновить все", self.resume),
                         ("Запомнить для BOOST", self.save_sel)):
            b = QPushButton(text); b.clicked.connect(fn); top.addWidget(b)
        top.insertWidget(0, QLabel("Сортировка:")); top.insertWidget(1, self.sort)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Процесс", "PID", "CPU %", "RAM МБ", "Статус"])
        self.table.setColumnWidth(0, 30); self.table.setColumnWidth(1, 240); self.table.setColumnWidth(5, 220)
        self.table.verticalHeader().hide()
        v.addLayout(top); v.addWidget(self.table); return w

    def _settings(self):
        w = QWidget(); v = QVBoxLayout(w)
        opts = [("auto_detect", "Автоопределение игр (полноэкранное окно)"),
                ("ask_on_game", "Спрашивать, включать ли Gaming Mode при запуске игры"),
                ("auto_enable", "Включать Gaming Mode автоматически (без вопроса)"),
                ("minimize_windows", "Сворачивать окна"), ("hide_taskbar", "Скрывать панель задач"),
                ("hide_desktop_icons", "Скрывать значки рабочего стола"),
                ("raise_game_priority", "Приоритет игры: Above Normal")]
        for k, t in opts:
            c = QCheckBox(t); c.setChecked(self.cfg[k]); c.toggled.connect(lambda s, k=k: self.cfg.set(k, s)); v.addWidget(c)
        v.addWidget(QLabel("Игры (выбранные вручную EXE):"))
        self.games = QListWidget(); self.games.addItems(self.cfg["games"]); v.addWidget(self.games)
        r = QHBoxLayout()
        for t, f in (("Добавить EXE…", self.add_game), ("Удалить", self.del_game)):
            b = QPushButton(t); b.clicked.connect(f); r.addWidget(b)
        v.addLayout(r); return w

    def _logtab(self):
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True); return self.log_view

    # ---------- действия ----------
    def refresh_procs(self):
        rows = P.snapshot(self.sort.currentText())
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsEnabled if r["reason"] else Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            if not r["reason"]:
                chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, (r["pid"], r["name"]))
            vals = [r["name"], str(r["pid"]), f"{r['cpu']:.1f}", f"{r['ram']:.0f}",
                    "Защищён: " + r["reason"] if r["reason"] else "можно трогать"]
            self.table.setItem(i, 0, chk)
            for j, t in enumerate(vals, 1):
                it = QTableWidgetItem(t); it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                if r["reason"]:
                    it.setForeground(QColor("#6b7280"))
                self.table.setItem(i, j, it)

    def _selected(self):
        return [self.table.item(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(self.table.rowCount())
                if self.table.item(i, 0).checkState() == Qt.CheckState.Checked]

    def close_sel(self):
        sel = self._selected()
        if sel and QMessageBox.question(self, "Закрыть процессы",
                "Будут закрыты (несохранённые данные пропадут):\n" + "\n".join(n for _, n in sel)) == QMessageBox.StandardButton.Yes:
            for pid, n in sel:
                self.engine.close(pid, n)
            self.refresh_procs()

    def suspend_sel(self):
        for pid, _ in self._selected():
            self.engine.suspend(pid)
        self.refresh_procs()

    def resume(self):
        self.engine.resume_all()

    def save_sel(self):
        names = sorted({n for _, n in self._selected()})
        self.cfg.set("suspend_on_boost", names); log.info("Список для BOOST: %s", names or "пуст")

    def add_game(self):
        f, _ = QFileDialog.getOpenFileName(self, "EXE игры", "", "Executable (*.exe)")
        if f and f not in self.cfg["games"]:
            self.cfg.set("games", self.cfg["games"] + [f]); self.games.addItem(f)

    def del_game(self):
        r = self.games.currentRow()
        if r >= 0:
            g = list(self.cfg["games"]); g.pop(r); self.cfg.set("games", g); self.games.takeItem(r)

    def suspend_shell(self):
        from .menu import WARN
        B = QMessageBox.StandardButton
        if QMessageBox.warning(self, "saf1rkaboost", WARN, B.Yes | B.No, B.No) == B.Yes:
            if not self.engine.shell_suspend():
                QMessageBox.information(self, "saf1rkaboost", "Не удалось отключить Explorer (см. лог).")
            self._state()

    def enable_mode(self):
        self.engine.enable(); self._state()
        if self.engine.game:
            self.showMinimized()

    def disable_mode(self):
        self.engine.disable(); self._state()
        if self.isMinimized():
            self.showNormal()

    def _state(self):
        on = self.engine.enabled
        self.status.setText(f"Gaming Mode: {'ON' if on else 'OFF'}")
        self.status.setStyleSheet(f"font-size:20px;font-weight:700;color:{'#19e6a7' if on else '#ff5c6c'}")
        g = self.engine.game
        self.game_lbl.setText(f"Игра: {g.name} (PID {g.pid}, {g.source})" if g else "Игра: не обнаружена")
        self.boost.setText("ON" if on else "BOOST"); self.boost.setEnabled(not on)
        sh, st = self.engine.shell_suspended, shell.state()
        self.restore_btn.setEnabled(on or sh or st == "SUSPENDED"); self.shell_btn.setEnabled(not sh)
        self.shell_lbl.setText(f"Explorer: {st}")
        self.shell_lbl.setStyleSheet("font-weight:700;color:" + ("#19e6a7" if st == "RUNNING" else "#ff5c6c"))

    # ---------- таймер ----------
    def _tick(self):
        self._n += 1
        try:
            self.engine.shell_watch(); self._state()
            c = monitor.cpu(); pct, used, total = monitor.ram(); g = self.gpu.value
            self.m_cpu.set(c, f"{c:.0f}%"); self.m_ram.set(pct, f"{used:.1f} / {total:.1f} ГБ")
            self.m_gpu.set(g or 0, f"{g:.0f}%" if g is not None else "н/д (только NVIDIA)")
            if self._n % 2 == 0:
                self._check_game()
        except Exception:
            log.exception("Ошибка в цикле мониторинга")

    def _check_game(self):
        g = self.engine.game
        if g:
            try:
                alive = g.proc.is_running()
            except psutil.Error:
                alive = False
            if not alive:
                log.info("Игра закрыта: %s", g.name)
                self.engine.game = None; self._prompted = None
                if self.engine.enabled or self.engine.shell_suspended:
                    self.disable_mode()
                self._state()
            return
        found = self.detector.find()
        if not found:
            return
        self.engine.attach_game(found); self._state(); log.info("Обнаружена игра: %s (%s)", found.name, found.source)
        if self.engine.enabled:
            return
        if self.cfg["auto_enable"]:
            self.enable_mode()
        elif self.cfg["ask_on_game"] and self._prompted != found.pid:
            self._prompted = found.pid
            if QMessageBox.question(self, "saf1rkaboost", f"Обнаружена игра {found.name}.\nВключить Gaming Mode?") == QMessageBox.StandardButton.Yes:
                self.enable_mode()

    def closeEvent(self, e):
        self.timer.stop(); self.gpu.stop(); self.engine.disable(); log.info("saf1rkaboost закрыт"); e.accept()
