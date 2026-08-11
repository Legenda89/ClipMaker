@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm ClipMaker.spec
echo.
echo Valmis: dist\ClipMaker.exe
pause
