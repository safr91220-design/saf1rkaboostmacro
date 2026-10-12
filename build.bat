@echo off
pip install -r requirements.txt
pyinstaller --noconfirm --onefile --windowed --name saf1rkaboost main.py
echo Готово: dist\saf1rkaboost.exe
pause
