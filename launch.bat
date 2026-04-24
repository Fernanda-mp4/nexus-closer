@echo off
cd /d "%~dp0"
REM Mata qualquer instancia anterior rodando em segundo plano
taskkill /F /IM pythonw.exe 2>nul
start "" "%~dp0.venv\Scripts\pythonw.exe" main.py
