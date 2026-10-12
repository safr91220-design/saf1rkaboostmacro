"""Автозапуск с Windows — только по желанию пользователя (ключ HKCU\\...\\Run, удаляется выключателем)."""
import os, sys

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "saf1rkaboost"

def _cmd():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    py = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{py}" "{os.path.abspath(sys.argv[0])}"'

def is_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            winreg.QueryValueEx(k, NAME)
        return True
    except OSError:
        return False

def set_enabled(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, _cmd())
        else:
            try:
                winreg.DeleteValue(k, NAME)
            except FileNotFoundError:
                pass
