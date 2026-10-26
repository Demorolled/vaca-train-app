@echo off
rem Start the train app on Windows: http://127.0.0.1:8137/
rem Same server as `python -m trainapp.server`; the launcher only pins the
rem working directory so the data directory resolves to this checkout.
setlocal
cd /d "%~dp0"
py -3 -m trainapp.server %*
if errorlevel 1 (
  echo.
  echo The server exited with an error. If "py" is not installed, run:
  echo     python -m trainapp.server
  pause
)
endlocal
