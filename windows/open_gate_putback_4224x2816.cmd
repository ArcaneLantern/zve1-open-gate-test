@echo off
rem ZV-E1 (firmware 2.02): put the 4224x2816 state back to stock (press C2 until the screen is at 3:2 first). After the 300 Mbps apply use open_gate_putback_4224x2816_300mbps.
rem WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing: run setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -I -B "tools\camera_tests\CT6_memory_read_check\zv_apply.py" putback4224 %*
echo.
pause
