@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python
py -3 open_database.py
goto finished
:python
python open_database.py
:finished
if errorlevel 1 pause
