@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
python manage.py migrate
python manage.py check
python manage.py runserver 127.0.0.1:8000
pause
