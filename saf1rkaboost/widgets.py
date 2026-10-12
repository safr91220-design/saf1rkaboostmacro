"""Общие элементы интерфейса в стиле NAYTERZ MACRO: переключатель, поле назначения клавиши, ползунок+поле, стили."""
from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox,
                               QStackedWidget, QWidget)
from . import keys

STYLE = """
QWidget{background:#0b0b0e;color:#e6e6ee;font-family:'Segoe UI';font-size:13px}
QLabel{background:transparent}
QFrame#side{background:#101014;border-right:1px solid #1f1f26}
QFrame#sub{background:#0e0e12;border-right:1px solid #1b1b22}
QLabel#brand{font-size:16px;font-weight:700;letter-spacing:1px}
QLabel#h1{font-size:22px;font-weight:700;letter-spacing:1px}
QLabel#note{color:#8a8a96;font-size:12px}
QLabel#rowlabel{color:#c9c9d3;font-weight:600;letter-spacing:.5px}
QLabel#section{color:#9b30ff;font-weight:700;letter-spacing:1.5px;font-size:11px}
QFrame#line{background:#25252c;min-height:1px;max-height:1px}
QPushButton{background:#17171c;border:1px solid #25252c;border-radius:8px;padding:8px 14px;color:#e6e6ee}
QPushButton:hover{border-color:#9b30ff;background:#1c1c23}
QPushButton:disabled{color:#55555f;border-color:#1c1c22}
QPushButton#nav{text-align:left;padding:13px 18px;border:none;border-left:3px solid transparent;border-radius:0;background:transparent;font-weight:600;letter-spacing:1px}
QPushButton#nav:hover{background:#15151a}
QPushButton#nav:checked{border-left:3px solid #9b30ff;background:#17131f;color:#ffffff}
QPushButton#primary{background:#8a2be2;border:none;font-weight:700;letter-spacing:1px;padding:9px 26px}
QPushButton#primary:hover{background:#9b30ff}
QPushButton#big{font-size:19px;font-weight:800;padding:20px;border:none;border-radius:12px;letter-spacing:2px;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6a1fc2,stop:1 #9b30ff)}
QPushButton#big:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7b2bd6,stop:1 #b25cff)}
QPushButton#big:disabled{background:#1c1c23;color:#6d6d79}
QPushButton#keyfield{background:#141418;border:1px solid #25252c;font-weight:700;min-width:150px}
QPushButton#keyfield[waiting="true"]{border:1px solid #9b30ff;color:#c58bff}
QPushButton#reset{background:transparent;border:none;color:#6d6d79;font-size:11px;padding:4px 8px}
QPushButton#reset:hover{color:#9b30ff}
QLineEdit,QSpinBox,QComboBox{background:#141418;border:1px solid #25252c;border-radius:6px;padding:6px 8px}
QLineEdit:focus,QSpinBox:focus,QComboBox:focus{border-color:#9b30ff}
QComboBox QAbstractItemView{background:#141418;selection-background-color:#4b1d7a;border:1px solid #25252c}
QSlider::groove:horizontal{height:4px;background:#25252c;border-radius:2px}
QSlider::sub-page:horizontal{background:#9b30ff;border-radius:2px}
QSlider::handle:horizontal{background:#b25cff;width:12px;height:12px;margin:-4px 0;border-radius:6px}
QProgressBar{background:#17171c;border:none;border-radius:4px;max-height:8px;min-height:8px}
QProgressBar::chunk{background:#9b30ff;border-radius:4px}
QPlainTextEdit,QListWidget{background:#0e0e12;border:1px solid #1f1f26;border-radius:8px;font-family:Consolas,monospace;font-size:12px}
QListWidget::item:selected{background:#2a1745}
QScrollBar:vertical{background:transparent;width:8px}
QScrollBar::handle:vertical{background:#2a2a33;border-radius:4px;min-height:20px}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
QMessageBox,QDialog,QInputDialog{background:#0e0e12}
"""

class Toggle(QWidget):
    """Переключатель с плавной анимацией."""
    toggled = Signal(bool)

    def __init__(self, checked=False):
        super().__init__()
        self.setFixedSize(46, 24); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on, self._k = bool(checked), 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(150); self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def _get(self): return self._k
    def _set(self, v): self._k = v; self.update()
    knob = Property(float, _get, _set)

    def isChecked(self): return self._on

    def setChecked(self, v):
        self._on = bool(v); self._anim.stop(); self._k = 1.0 if self._on else 0.0; self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self._on = not self._on
            self._anim.stop(); self._anim.setStartValue(self._k); self._anim.setEndValue(1.0 if self._on else 0.0)
            self._anim.start(); self.toggled.emit(self._on)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._k
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(int(42 + 113 * t), int(42 + 6 * t), int(50 + 205 * t)))
        p.drawRoundedRect(self.rect(), 12, 12)
        p.setBrush(QColor("#ffffff")); p.drawEllipse(int(3 + 22 * t), 3, 18, 18)

class KeyField(QPushButton):
    """Клик → режим ожидания → нажмите клавишу/кнопку мыши. Esc — отмена. mode='combo' — для горячих клавиш."""
    changed = Signal(str)

    def __init__(self, mode="key", allow_lr=True):
        super().__init__("—")
        self.mode, self.allow_lr, self.value, self.waiting = mode, allow_lr, "", False
        self.setObjectName("keyfield"); self.setFixedHeight(34)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self._begin)

    def set(self, v):
        self.value = v; self._paint()

    def _paint(self):
        self.setText("PRESS A KEY…" if self.waiting else (self.value or "—"))
        self.setProperty("waiting", self.waiting); self.style().unpolish(self); self.style().polish(self)

    def _begin(self):
        if not self.waiting:
            self.waiting = True; self.grabKeyboard(); self.grabMouse(); self._paint()

    def _end(self):
        if self.waiting:
            self.waiting = False; self.releaseKeyboard(); self.releaseMouse(); self._paint()

    def _take(self, name):
        self.value = name; self._end(); self.changed.emit(name)

    def keyPressEvent(self, e):
        if not self.waiting:
            return super().keyPressEvent(e)
        if e.isAutoRepeat():
            return
        if e.key() == Qt.Key.Key_Escape:
            self._end(); return
        name = keys.vk_name(e.nativeVirtualKey())
        if not name:
            return
        if self.mode == "combo":
            if name in ("CTRL", "ALT", "SHIFT"):
                return
            m, mods = e.modifiers(), []
            for flag, n in ((Qt.KeyboardModifier.ControlModifier, "CTRL"), (Qt.KeyboardModifier.AltModifier, "ALT"),
                            (Qt.KeyboardModifier.ShiftModifier, "SHIFT"), (Qt.KeyboardModifier.MetaModifier, "WIN")):
                if m & flag:
                    mods.append(n)
            if not mods:
                return
            name = "+".join(mods + [name])
        self._take(name)

    def mousePressEvent(self, e):
        if not self.waiting:
            return super().mousePressEvent(e)
        if self.mode == "combo":
            return
        b = e.button()
        name = {Qt.MouseButton.MiddleButton: "MOUSE_MIDDLE", Qt.MouseButton.BackButton: "XBUTTON1",
                Qt.MouseButton.ForwardButton: "XBUTTON2"}.get(b)
        if name is None and self.allow_lr:
            name = {Qt.MouseButton.LeftButton: "MOUSE_LEFT", Qt.MouseButton.RightButton: "MOUSE_RIGHT"}.get(b)
        self._take(name) if name else self._end()      # лев./прав. кнопка отменяет ввод, если она недопустима

    def mouseReleaseEvent(self, e):
        if not self.waiting:
            super().mouseReleaseEvent(e)

    def focusOutEvent(self, e):
        self._end(); super().focusOutEvent(e)

class SliderSpin(QWidget):
    """Ползунок и поле ввода синхронизированы; допустимый диапазон ограничен."""
    changed = Signal(int)

    def __init__(self, lo, hi):
        super().__init__()
        self.sl = QSlider(Qt.Orientation.Horizontal); self.sl.setRange(lo, hi)
        self.sp = QSpinBox(); self.sp.setRange(lo, hi); self.sp.setSuffix(" ms"); self.sp.setFixedWidth(92)
        self.sp.setToolTip(f"Допустимо: {lo}–{hi} мс")
        h = QHBoxLayout(self); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(12)
        h.addWidget(self.sl, 1); h.addWidget(self.sp)
        self.sl.valueChanged.connect(lambda v: self._sync(v, self.sp))
        self.sp.valueChanged.connect(lambda v: self._sync(v, self.sl))

    def _sync(self, v, other):
        other.blockSignals(True); other.setValue(v); other.blockSignals(False); self.changed.emit(v)

    def set(self, v):
        for w in (self.sl, self.sp):
            w.blockSignals(True); w.setValue(int(v)); w.blockSignals(False)

    def value(self):
        return self.sp.value()

class FadeStack(QStackedWidget):
    """Стек страниц с плавным появлением."""
    def fade_to(self, idx):
        if idx == self.currentIndex():
            return
        self.setCurrentIndex(idx)
        w = self.currentWidget(); eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self); a.setDuration(180)
        a.setStartValue(0.0); a.setEndValue(1.0); a.finished.connect(lambda: w.setGraphicsEffect(None)); a.start()
        self._a = a

def make_row(label, widget, reset=None, expand=False):
    """Строка настройки: подпись · элемент · кнопка RESET."""
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(12)
    l = QLabel(label); l.setObjectName("rowlabel"); l.setFixedWidth(160)
    h.addWidget(l); h.addWidget(widget, 1 if expand else 0)
    if not expand:
        h.addStretch(1)
    if reset:
        b = QPushButton("RESET"); b.setObjectName("reset"); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(reset); h.addWidget(b)
    return w

def hline():
    from PySide6.QtWidgets import QFrame
    f = QFrame(); f.setObjectName("line"); return f
