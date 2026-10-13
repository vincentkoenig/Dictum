@echo off
rem Startet Dictum. Doppelklick genügt.
rem -X utf8 sorgt dafür, dass Umlaute in der Konsole richtig angezeigt werden.
cd /d "%~dp0"
.venv\Scripts\python.exe -X utf8 -m dictum
pause
