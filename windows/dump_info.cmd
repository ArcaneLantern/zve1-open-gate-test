@echo off
rem ZV-E1 (firmware 2.02): read-only dump of facts for the port (logs, tables, memory map).
rem READ-ONLY: nothing in the camera's memory or settings is changed. Extra options are passed on, e.g.  --dry-run  --selftest
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing: run setup.cmd first.
  pause
  exit /b 1
)
set /p FWV=Firmware version shown in the camera's menu (Setup, Version), e.g. 2.02:
".venv\Scripts\python.exe" -I -B "tools\camera_tests\CT6_memory_read_check\zv_run.py" dump --go --firmware-shown %FWV% %*
echo.
echo The results are in windows\camera_private (newest folder). Zip that folder and send it back.
pause
