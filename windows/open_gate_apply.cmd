@echo off
rem ZV-E1 (firmware 2.02): apply the default state: 3840x2560 open gate, file headers 3840x2560 (no remux needed), the screen at 3:2 and the C2 preview cycle (six steps, the first one the raw write buffer, then one read-only session).
rem WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
rem Extra options are passed on, e.g.  --no-meta  --dry-run. Cold boot with the battery out before running, and set Proxy Recording to Off.
rem The power switch alone can leave the encoder side at 2560 (a 4K clip then came out 3840x2560, 16:9 picture letterboxed): pull the battery before normal 4K.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing: run setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -I -B "tools\camera_tests\CT6_memory_read_check\zv_apply.py" apply %*
echo.
pause
