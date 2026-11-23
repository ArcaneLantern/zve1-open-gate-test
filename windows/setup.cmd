@echo off
rem Creates windows\.venv with the two packages the launchers need (pyusb, pycryptodomex). Needs Python 3.10 or later (py launcher).
cd /d "%~dp0"
py -3 -m venv .venv || (echo Python 3 not found: install it from python.org, with the py launcher. & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Done. Also needed once: the libusb-win32 driver for the camera (Zadig), see README.md.
pause
