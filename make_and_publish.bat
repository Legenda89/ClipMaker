@echo off
REM Agent / batch helper: 30s best-clip + cover + publish
REM Usage:
REM   make_and_publish.bat "C:\path\song.mp3" "C:\path\cover.jpg" "Otsikko tähän"
cd /d "%~dp0"
if "%~1"=="" (
  echo Kaytto: make_and_publish.bat musa.mp3 kansikuva.jpg "Otsikko"
  exit /b 1
)
if "%~2"=="" (
  echo Puuttuu kansikuva
  exit /b 1
)
set TITLE=%~3
if "%TITLE%"=="" set TITLE=%~n1
python run.py make --audio "%~1" --image "%~2" --duration 30 --preset tiktok --title "%TITLE%" --publish youtube,tiktok --json
