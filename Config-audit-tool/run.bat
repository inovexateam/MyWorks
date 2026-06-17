@echo off
cd /d "%~dp0"
echo Installing dependencies (first run only)...
pip install -r requirements.txt --quiet
echo Starting Config Audit tool...
python app.py
pause
