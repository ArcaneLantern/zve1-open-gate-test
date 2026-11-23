@echo off
rem ZV-E1 (firmware 2.02): apply only the three open-gate steps, without the two screen steps.
rem WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing: run setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -I -B "tools\camera_tests\CT6_memory_read_check\zv_apply.py" apply --no-screen %*
echo.
pause
