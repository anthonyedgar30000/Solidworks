@echo off
setlocal
cd /d "%~dp0"

where dotnet >nul 2>nul
if errorlevel 1 (
  echo ERROR: dotnet SDK was not found on PATH.
  echo Install/use a .NET 8 SDK, then rerun this file.
  exit /b 1
)

if not exist "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SolidWorks.Interop.sldworks.dll" (
  echo ERROR: SOLIDWORKS interop assembly not found at expected path.
  exit /b 1
)

dotnet build CadGrounded.SolidWorksWorker.csproj -c Release
if errorlevel 1 exit /b 1

echo.
echo Build complete.
echo EXE:
echo %CD%\bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe
