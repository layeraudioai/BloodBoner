@echo off
setlocal EnableExtensions

rem Build the Switch 2 Horizon homebrew NRO profile. Requires a devkitPro/libnx
rem toolchain that supports the Switch 2 SDK/target; this profile alone does not
rem add Switch 2-specific runtime support.
set "TARGET_PROFILE=switch2"
set "PROJECT_ROOT=%~dp0"
set "SWITCH_DIR=%PROJECT_ROOT%switch"
set "OUTPUT_DIR=%PROJECT_ROOT%dist"
if not "%~1"=="" set "OUTPUT_DIR=%~1"

if not defined DEVKITPRO set "DEVKITPRO=C:\devkitPro"
if not exist "%DEVKITPRO%\libnx\switch_rules" (
  echo ERROR: libnx switch_rules not found under "%DEVKITPRO%".
  echo Install a devkitPro/libnx toolchain supporting Switch 2, then set DEVKITPRO.
  exit /b 2
)
if exist "%DEVKITPRO%\msys2\usr\bin" set "PATH=%DEVKITPRO%\msys2\usr\bin;%PATH%"
where make.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: GNU make.exe was not found. Install it with devkitPro or add it to PATH.
  exit /b 2
)

pushd "%SWITCH_DIR%" || exit /b 2
echo Building %TARGET_PROFILE% NRO...
make.exe TARGET_PROFILE=%TARGET_PROFILE%
set "BUILD_RESULT=%ERRORLEVEL%"
popd
if not "%BUILD_RESULT%"=="0" (
  echo ERROR: devkitPro build failed with exit code %BUILD_RESULT%.
  exit /b %BUILD_RESULT%
)

set "NRO_NAME=bloodboner-bootstrap-%TARGET_PROFILE%.nro"
set "NRO_SOURCE="
for /f "delims=" %%F in ('dir /b /s "%SWITCH_DIR%\%NRO_NAME%" 2^>nul') do if not defined NRO_SOURCE set "NRO_SOURCE=%%F"
if not defined NRO_SOURCE (
  echo ERROR: build succeeded but %NRO_NAME% was not found under switch\.
  exit /b 3
)
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
if errorlevel 1 (
  echo ERROR: Could not create output directory "%OUTPUT_DIR%".
  exit /b 3
)
copy /y "%NRO_SOURCE%" "%OUTPUT_DIR%\bloodboner-switch2.nro" >nul
if errorlevel 1 (
  echo ERROR: Could not copy the NRO to "%OUTPUT_DIR%".
  exit /b 3
)
echo Built Switch 2 profile bootstrap: "%OUTPUT_DIR%\bloodboner-switch2.nro"
echo Note: actual Switch 2 toolchain and hardware support are not verified.
exit /b 0
