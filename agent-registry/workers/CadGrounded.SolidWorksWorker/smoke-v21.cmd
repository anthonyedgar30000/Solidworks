@echo off
setlocal
cd /d "%~dp0"

set "EXE=%CD%\bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe"

if not exist "%EXE%" (
  echo ERROR: worker executable not found. Run build.cmd first.
  exit /b 1
)

echo === STATUS ===
"%EXE%" status
if errorlevel 1 exit /b 1

echo.
echo === CLOSEST DISTANCE: AR60 to Bottle 3 ===
"%EXE%" closest-distance --a "6130460_03_AR60_NATIVE_PORTABLE_V18-2" --b "BENCH_BOTTLE_D48_H180-3"
exit /b %errorlevel%
