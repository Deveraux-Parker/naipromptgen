@echo off
echo Setting up environment for NAI Prompt Tag Search and Gen...

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. Please install Python 3.7 or higher and try again.
    exit /b 1
)

REM Check if virtual environment exists, if not create it
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install or upgrade pip
python -m pip install --upgrade pip

REM Install required packages
echo Installing required packages...
pip install -r requirements.txt

REM Run the main script
echo Starting the application...
python main.py

REM Deactivate virtual environment
deactivate

echo Application closed. Press any key to exit.
pause >nul