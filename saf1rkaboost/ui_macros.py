"""Вкладка MACROS: профили, шесть категорий (EDIT/DOUBLE/SINGLE/DROP/SIT/PICKAXE), назначение клавиш, задержки."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)
from . import keys, macro_store as ms
from .logger import log
from .widgets import FadeStack, KeyField, SliderSpin, Toggle, hline, make_row

TITLES = {"EDIT": ("EDIT", "Редактирование"), "DOUBLE": ("DOUBLE EDIT", "Двойное редактирование"),
          "SINGLE": ("SINGLE EDIT", "Одиночное редактирование"), "DROP": ("DROP", "Выброс предмета"),
          "SIT": ("SIT", "Посадка / эмоция"), "PICKAXE": ("PICKAXE", "Быстрая кирка")}

class CategoryPage(QWidget):
    def __init__(self, cat, store, apply):
        super().__init__()
        self.cat, self.store, self.apply, self._loading = cat, store, apply, False
        self.sel, self.edt, self.act = KeyField(), KeyField(), KeyField(allow_lr=False)
        self.seq = QLineEdit(); self.seq.setMinimumWidth(320)
        self.ed, self.kd = SliderSpin(ms.D_MIN, ms.D_MAX), SliderSpin(ms.D_MIN, ms.D_MAX)
        self.info = QLabel(); self.info.setWordWrap(True); self.info.setObjectName("note")
        self.status = QLabel(); self.status.setObjectName("note")
        self.toggle = Toggle()
        v = QVBoxLayout(self); v.setContentsMargins(26, 20, 26, 14); v.setSpacing(14)
        t = QLabel(TITLES[cat][0]); t.setObjectName("h1")
        s = QLabel(TITLES[cat][1].upper()); s.setObjectName("note")
        v.addWidget(t); v.addWidget(s); v.addWidget(hline())
        for label, w, key, exp in (("SELECT KEY", self.sel, "select", False), ("EDIT KEY", self.edt, "edit", False),
                                   ("ACTIVATE KEY", self.act, "activate", False), ("SEQUENCE", self.seq, "sequence", True),
                                   ("EDIT DELAY (MS)", self.ed, "edit_delay", True), ("KEY DELAY (MS)", self.kd, "key_delay", True)):
            v.addWidget(make_row(label, w, lambda _=False, k=key: self.reset(k), exp))
        hint = QLabel("SEQUENCE: SELECT, EDIT, KEY:F5 — нажатие · +EDIT / -EDIT — зажать / отпустить · "
                      "W:EDIT, W:KEY, W:25 — пауза (мс). Максимум 32 шага.")
        hint.setObjectName("note"); hint.setWordWrap(True)
        v.addWidget(hint); v.addWidget(self.info); v.addStretch(1); v.addWidget(hline())
        save = QPushButton("SAVE"); save.setObjectName("primary"); save.clicked.connect(lambda: self.save())
        f = QHBoxLayout(); f.addWidget(self.status, 1); f.addWidget(save); f.addSpacing(12)
        f.addWidget(QLabel("ENABLE")); f.addWidget(self.toggle); v.addLayout(f)
        for w in (self.sel, self.edt):
            w.changed.connect(self._edited)
        self.act.changed.connect(self._edited)
        self.seq.textChanged.connect(self._edited); self.ed.changed.connect(self._edited); self.kd.changed.connect(self._edited)
        self.toggle.toggled.connect(self._toggle)

    def load(self):
        m = self.store.profile()["macros"][self.cat]; self._loading = True
        self.sel.set(m["select"]); self.edt.set(m["edit"]); self.act.set(m["activate"])
        self.seq.setText(m["sequence"]); self.ed.set(m["edit_delay"]); self.kd.set(m["key_delay"])
        self.toggle.setChecked(m["enabled"]); self._loading = False
        self.status.setText(""); self._refresh()

    def collect(self):
        return {"select": self.sel.value, "edit": self.edt.value, "activate": self.act.value,
                "sequence": self.seq.text().strip(), "edit_delay": self.ed.value(), "key_delay": self.kd.value(),
                "enabled": self.toggle.isChecked()}

    def reset(self, key):
        d = ms.default_macros()[self.cat][key]; self._loading = True
        {"select": self.sel.set, "edit": self.edt.set, "activate": self.act.set, "sequence": self.seq.setText,
         "edit_delay": self.ed.set, "key_delay": self.kd.set}[key](d)
        self._loading = False; self._edited()

    def _msg(self, text, bad=False):
        self.status.setText(text); self.status.setStyleSheet("color:%s" % ("#ff5c6c" if bad else "#9b30ff"))

    def _edited(self, *_):
        if not self._loading:
            self._msg("● UNSAVED", True); self._refresh()

    def _refresh(self):
        d, lines = self.collect(), []
        if d["activate"] in ("MOUSE_LEFT", "MOUSE_RIGHT"):
            lines.append("ACTIVATE: левая/правая кнопка мыши не допускаются")
        try:
            ms.parse_sequence(d["sequence"], d)
        except ValueError as e:
            lines.append(f"SEQUENCE: {e}")
        lines += [m for m, _ in self.store.conflicts_for(self.cat, d)]
        self.info.setText("\n".join("⚠ " + x for x in lines)); self.info.setStyleSheet("color:#ffb454")

    def save(self, enabled=None):
        d = self.collect()
        if enabled is not None:
            d["enabled"] = enabled
        try:
            ms.parse_sequence(d["sequence"], d)
        except ValueError as e:
            self._msg(f"SEQUENCE: {e}", True); return False
        if d["activate"] in ("MOUSE_LEFT", "MOUSE_RIGHT"):
            self._msg("ACTIVATE: недопустимая кнопка", True); return False
        if d["enabled"] and any(b for _, b in self.store.conflicts_for(self.cat, d)):
            self._msg("Конфликт клавиш — макрос не включён", True); log.warning("%s: конфликт ACTIVATE KEY", self.cat); return False
        self.store.set_macro(self.cat, d); self._msg("✔ SAVED"); self._refresh(); self.apply()
        log.info("Макрос %s сохранён (%s)", self.cat, "ВКЛ" if d["enabled"] else "выкл")
        return True

    def _toggle(self, on):
        if self._loading:
            return
        if not on:                       # выключение всегда разрешено и мгновенно
            self.store.profile()["macros"][self.cat]["enabled"] = False; self.store.save()
            self.apply(); self._msg("Macro disabled"); return
        if not self.save(enabled=True):
            self.toggle.setChecked(False)

class MacrosPage(QWidget):
    profile_changed = Signal()

    def __init__(self, store, apply, set_master):
        super().__init__()
        self.store, self.apply, self.set_master = store, apply, set_master
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        top = QHBoxLayout(); top.setContentsMargins(20, 14, 20, 8); top.setSpacing(8)
        self.combo = QComboBox(); self.combo.setMinimumWidth(170); self.combo.currentTextChanged.connect(self._pick)
        top.addWidget(QLabel("PROFILE")); top.addWidget(self.combo)
        for text, fn in (("RENAME", self.rename), ("COPY", self.copy), ("NEW", self.new), ("DELETE", self.delete),
                         ("IMPORT", self.imp), ("EXPORT", self.exp)):
            b = QPushButton(text); b.clicked.connect(fn); top.addWidget(b)
        top.addStretch(1)
        self.engine_toggle = Toggle(store.settings["engine_on"]); self.engine_toggle.toggled.connect(self._master)
        top.addWidget(QLabel("MACRO ENGINE")); top.addWidget(self.engine_toggle)
        gate = QHBoxLayout(); gate.setContentsMargins(20, 0, 20, 10); gate.setSpacing(10)
        self.game = QLineEdit(); self.game.setPlaceholderText("game.exe — например FortniteClient-Win64-Shipping.exe")
        self.game.editingFinished.connect(self._gate)
        self.only = Toggle(); self.only.toggled.connect(self._gate)
        gate.addWidget(QLabel("GAME EXE")); gate.addWidget(self.game, 1); gate.addWidget(QLabel("ONLY WHEN GAME IS FOCUSED")); gate.addWidget(self.only)
        v.addLayout(top); v.addLayout(gate); v.addWidget(hline())
        body = QHBoxLayout(); body.setSpacing(0)
        from PySide6.QtWidgets import QFrame
        side = QFrame(); side.setObjectName("sub"); side.setFixedWidth(150)
        sv = QVBoxLayout(side); sv.setContentsMargins(0, 10, 0, 10); sv.setSpacing(0)
        self.stack, self.pages, self.grp = FadeStack(), {}, QButtonGroup(self)
        for i, c in enumerate(ms.CATS):
            b = QPushButton(c); b.setObjectName("nav"); b.setCheckable(True); b.setChecked(i == 0)
            self.grp.addButton(b, i); sv.addWidget(b)
            p = CategoryPage(c, store, apply); self.pages[c] = p; self.stack.addWidget(p)
        sv.addStretch(1)
        self.grp.idClicked.connect(self.stack.fade_to)
        body.addWidget(side); body.addWidget(self.stack, 1); v.addLayout(body, 1)
        self.refresh()

    def refresh(self):
        self.combo.blockSignals(True); self.combo.clear(); self.combo.addItems(self.store.names())
        self.combo.setCurrentText(self.store.active); self.combo.blockSignals(False)
        p = self.store.profile()
        self.game.setText(p["game_exe"]); self.only.setChecked(p["only_in_game"])
        for pg in self.pages.values():
            pg.load()

    def _changed(self):
        self.refresh(); self.apply(); self.profile_changed.emit()

    def _pick(self, name):
        if name and name != self.store.active:
            self.store.set_active(name); log.info("Профиль: %s", name); self._changed()

    def _gate(self, *_):
        p = self.store.profile()
        p["game_exe"], p["only_in_game"] = self.game.text().strip()[:260], self.only.isChecked(); self.store.save(); self.apply()

    def _master(self, on):
        if not self.set_master(on):
            self.engine_toggle.setChecked(False)

    def _ask(self, title, text=""):
        t, ok = QInputDialog.getText(self, title, "Name:", text=text)
        return t.strip() if ok and t.strip() else None

    def rename(self):
        n = self._ask("Rename profile", self.store.active)
        if n:
            try:
                self.store.rename(n); log.info("Профиль переименован: %s", n); self._changed()
            except ValueError as e:
                QMessageBox.warning(self, "saf1rka_boost", str(e))

    def new(self):
        n = self._ask("New profile", "New profile")
        if n:
            self.store.new(n); log.info("Создан профиль %s", self.store.active); self._changed()

    def copy(self):
        n = self.store.copy(); log.info("Профиль скопирован: %s", n); self._changed()

    def delete(self):
        if QMessageBox.question(self, "saf1rka_boost", f"Удалить профиль «{self.store.active}»?") == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete(); log.info("Профиль удалён"); self._changed()
            except ValueError as e:
                QMessageBox.warning(self, "saf1rka_boost", str(e))

    def imp(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import profile", "", "JSON (*.json)")
        if path:
            try:
                n = self.store.import_profile(path); log.info("Импортирован профиль %s", n); self._changed()
            except Exception as e:
                log.warning("Импорт не удался: %s", e); QMessageBox.warning(self, "saf1rka_boost", f"Импорт не удался:\n{e}")

    def exp(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export profile", f"{self.store.active}.json", "JSON (*.json)")
        if path:
            try:
                self.store.export_profile(path); log.info("Профиль экспортирован: %s", path)
            except OSError as e:
                QMessageBox.warning(self, "saf1rka_boost", f"Экспорт не удался:\n{e}")
