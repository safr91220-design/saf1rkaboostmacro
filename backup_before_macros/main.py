import sys

def main():
    if sys.platform != "win32":
        print("saf1rkaboost работает только в Windows 10/11."); return 1
    from saf1rkaboost.logger import setup, log
    setup()
    if "--watchdog" in sys.argv:          # служебный режим: аварийное восстановление Explorer
        from saf1rkaboost.shell import watchdog
        watchdog(int(sys.argv[sys.argv.index("--watchdog") + 1])); return 0
    if "--restore" in sys.argv:           # ручное аварийное восстановление
        from saf1rkaboost.desktop import force_restore
        from saf1rkaboost.shell import restore
        force_restore(); restore(); return 0
    if "--test-shell" in sys.argv:        # тест: Explorer off на 10 с, затем авто-возврат
        import ctypes, time
        from saf1rkaboost import shell
        mb = ctypes.windll.user32.MessageBoxW
        if mb(0, "Explorer будет отключён на 10 секунд и затем восстановлен автоматически.\nСохраните работу. Продолжить?",
              "saf1rkaboost: тест", 0x24) != 6:
            return 0
        ok = False
        try:
            ok = shell.suspend(); time.sleep(10)
        finally:
            back = shell.restore()
        mb(0, f"Отключение: {'успешно' if ok else 'не удалось'}\nВосстановление: "
              f"{'успешно' if back else 'НЕ УДАЛОСЬ: Ctrl+Shift+Esc → Запустить новую задачу → explorer.exe'}",
           "saf1rkaboost: тест", 0x40)
        return 0
    from PySide6.QtWidgets import QApplication
    from saf1rkaboost.ui import MainWindow
    from saf1rkaboost.menu import MenuWindow
    app = QApplication(sys.argv)
    win = MainWindow() if "--full" in sys.argv else MenuWindow()

    def hook(t, v, tb):
        log.critical("Необработанная ошибка", exc_info=(t, v, tb))
        try:
            win.engine.disable()
        except Exception:
            pass
    sys.excepthook = hook
    app.aboutToQuit.connect(win.engine.disable)
    win.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
