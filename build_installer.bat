@echo off
setlocal enabledelayedexpansion
echo ============================================
echo  MTT Windows Infinite Optimizer - Build Script
echo ============================================
echo.

echo [1/8] Reading version from version.json...
REM No pipe in the command below on purpose: a '|' inside for /f backticks
REM gets eaten by cmd before PowerShell ever sees it.
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "(ConvertFrom-Json (Get-Content -Raw version.json)).version"`) do set APPVERSION=%%v
if "%APPVERSION%"=="" (
    echo ERROR: Could not read the version from version.json.
    pause
    exit /b 1
)
echo    Version: %APPVERSION%
set SETUPNAME=MTT_InfiniteOptimizer_Setup_v%APPVERSION%.exe
echo    Installer will be: %SETUPNAME%
echo.

REM ===========================================================================
REM Code-signing configuration. See docs/SIGNING.md for the working recipe.
REM
REM Credentials are read from the environment ONLY - this repo is public, so
REM nothing secret is ever stored in this file:
REM     MTT_SIGN_USER   SSL.com account username
REM     MTT_SIGN_PASS   SSL.com account password
REM     MTT_SIGN_TOTP   base64 TOTP secret from the cert page (NOT base32)
REM
REM If any of the three is unset, signing is skipped and the build still
REM produces a working (unsigned) installer.
REM ===========================================================================
echo [2/8] Checking code-signing configuration...
set "SIGNING=0"
set "CODESIGNTOOL=C:\Dev\CodeSignTool"
set "SIGNTMP=%TEMP%\mtt_codesign"

REM Preferred signtool (per docs/SIGNING.md), with a fallback search.
set "SIGNTOOL=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
if not exist "!SIGNTOOL!" (
    set "SIGNTOOL="
    for /f "delims=" %%s in ('dir /b /s /a-d "%ProgramFiles(x86)%\Windows Kits\10\bin\*\x64\signtool.exe" 2^>nul') do set "SIGNTOOL=%%s"
)

set "SIGN_MISSING="
if not defined MTT_SIGN_USER set "SIGN_MISSING=!SIGN_MISSING! MTT_SIGN_USER"
if not defined MTT_SIGN_PASS set "SIGN_MISSING=!SIGN_MISSING! MTT_SIGN_PASS"
if not defined MTT_SIGN_TOTP set "SIGN_MISSING=!SIGN_MISSING! MTT_SIGN_TOTP"

if defined SIGN_MISSING (
    echo    Code signing is OFF - these environment variables are not set:
    echo     !SIGN_MISSING!
    echo.
    echo    The build will continue and produce an UNSIGNED installer.
    echo    To produce a SIGNED build, set all three and re-run this script:
    echo.
    echo      set MTT_SIGN_USER=MacroTechTitan
    echo      set MTT_SIGN_PASS=your-ssl-com-account-password
    echo      set MTT_SIGN_TOTP=base64-totp-secret-from-the-cert-page
    echo.
) else (
    if not exist "!CODESIGNTOOL!\CodeSignTool.bat" (
        echo    ERROR: signing credentials are set, but CodeSignTool was not found at:
        echo           !CODESIGNTOOL!\CodeSignTool.bat
        pause
        exit /b 1
    )
    if not defined SIGNTOOL (
        echo    ERROR: signing credentials are set, but signtool.exe was not found.
        echo           Install the Windows SDK signing tools, then re-run.
        pause
        exit /b 1
    )
    set "SIGNING=1"
    echo    Code signing is ON - credentials found in the environment.
    echo    CodeSignTool: !CODESIGNTOOL!\CodeSignTool.bat
    echo    signtool:     !SIGNTOOL!
)
echo.

echo [3/8] Installing Python dependencies...
REM "python -m" everywhere so pip, PyInstaller and the runtime-DLL lookup
REM below all use the same interpreter.
python -m pip install flask psutil apscheduler pywebview pyinstaller
echo.

echo [4/8] Building executable with PyInstaller...
REM ===========================================================================
REM Runtime DLLs. A clean Windows machine has no Python and often no VC++
REM runtime, so force-bundle both instead of trusting PyInstaller's detection.
REM They are resolved from whichever Python runs this build (sys.base_prefix
REM also sees through a venv), then its DLLs\ subdir, then System32 - nothing
REM is hardcoded to one build machine.
REM ===========================================================================
set "PYBASE="
for /f "usebackq delims=" %%p in (`python -c "import sys; print(sys.base_prefix)"`) do set "PYBASE=%%p"
set "PYDLL="
for /f "usebackq delims=" %%p in (`python -c "import sys; print(f'python{sys.version_info[0]}{sys.version_info[1]}.dll')"`) do set "PYDLL=%%p"
if "%PYBASE%"=="" (
    echo ERROR: could not locate the Python install - is python on PATH?
    pause
    exit /b 1
)
if "%PYDLL%"=="" (
    echo ERROR: could not determine the Python DLL name.
    pause
    exit /b 1
)
set "RUNTIME_DLLS=vcruntime140.dll vcruntime140_1.dll python3.dll %PYDLL%"
echo    Python install: %PYBASE%
echo    Force-bundling runtime DLLs:
set "ADDBIN="
set "DLL_MISSING="
for %%d in (%RUNTIME_DLLS%) do (
    set "FOUND="
    for %%s in ("%PYBASE%" "%PYBASE%\DLLs" "%SystemRoot%\System32") do (
        if not defined FOUND if exist "%%~s\%%d" set "FOUND=%%~s\%%d"
    )
    if defined FOUND (
        echo      %%d  from  !FOUND!
        set ADDBIN=!ADDBIN! --add-binary "!FOUND!;."
    ) else (
        set "DLL_MISSING=!DLL_MISSING! %%d"
    )
)
if defined DLL_MISSING (
    echo ERROR: required runtime DLLs not found on this build machine:!DLL_MISSING!
    echo        Looked in %PYBASE%, %PYBASE%\DLLs and %SystemRoot%\System32.
    pause
    exit /b 1
)
echo.

REM static\branding (icons, logos, splash) ships via the static add-data below.
python -m PyInstaller --noconfirm --onedir --windowed ^
    --uac-admin ^
    !ADDBIN! ^
    --name "MTT Windows Infinite Optimizer" ^
    --icon "static\branding\mtt-app.ico" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "settings.json;." ^
    --add-data "version.json;." ^
    --hidden-import "apscheduler.triggers.cron" ^
    --hidden-import "apscheduler.schedulers.background" ^
    --hidden-import "apscheduler.triggers.interval" ^
    --hidden-import "apscheduler.triggers.date" ^
    --hidden-import "webview" ^
    --exclude-module "resend" ^
    --exclude-module "httpx" ^
    --exclude-module "anyio" ^
    desktop_launcher.py
echo.

if not exist "dist\MTT Windows Infinite Optimizer\MTT Windows Infinite Optimizer.exe" (
    echo ERROR: PyInstaller build failed. Check the output above for errors.
    pause
    exit /b 1
)

echo    PyInstaller build complete.
echo    Output: dist\MTT Windows Infinite Optimizer\
echo.

REM Confirm the runtime DLLs actually landed in dist. PyInstaller 6 puts
REM them in _internal\; older layouts put them next to the exe.
set "DISTAPP=dist\MTT Windows Infinite Optimizer"
echo    Runtime DLLs shipped in dist:
set "SHIP_MISSING="
for %%d in (%RUNTIME_DLLS%) do (
    if exist "%DISTAPP%\_internal\%%d" (
        echo      [OK]      _internal\%%d
    ) else if exist "%DISTAPP%\%%d" (
        echo      [OK]      %%d
    ) else (
        echo      [MISSING] %%d
        set "SHIP_MISSING=!SHIP_MISSING! %%d"
    )
)
echo    All VC++ / Python runtime DLLs present in dist:
for %%f in ("%DISTAPP%\_internal\vcruntime*.dll" "%DISTAPP%\_internal\msvcp*.dll" "%DISTAPP%\_internal\python3*.dll" "%DISTAPP%\vcruntime*.dll" "%DISTAPP%\msvcp*.dll" "%DISTAPP%\python3*.dll") do echo      %%~nxf
if defined SHIP_MISSING (
    echo.
    echo ERROR: runtime DLLs missing from dist:!SHIP_MISSING!
    echo        The installer would fail on a clean machine - aborting.
    pause
    exit /b 1
)
echo.

REM ===========================================================================
REM Stage 1 of 2: sign the APPLICATION EXE. This must happen AFTER PyInstaller
REM and BEFORE makensis, so the signed exe is the one packaged into the
REM installer.
REM ===========================================================================
echo [5/8] Signing the application executable...
if "!SIGNING!"=="1" (
    call :sign_file "dist\MTT Windows Infinite Optimizer\MTT Windows Infinite Optimizer.exe"
    if errorlevel 1 (
        echo.
        echo ERROR: signing the application exe failed - aborting the build.
        echo        The installer was NOT built, so an unsigned app cannot
        echo        slip into a release by mistake.
        pause
        exit /b 1
    )
) else (
    echo    Skipped - no signing credentials in the environment.
)
echo.

echo [6/8] Building NSIS installer...
echo    Looking for NSIS...
set MAKENSIS=
where makensis >nul 2>nul
if %errorlevel% equ 0 set MAKENSIS=makensis
if "!MAKENSIS!"=="" if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set MAKENSIS=%ProgramFiles(x86)%\NSIS\makensis.exe
if "!MAKENSIS!"=="" if exist "%ProgramFiles%\NSIS\makensis.exe" set MAKENSIS=%ProgramFiles%\NSIS\makensis.exe

if "!MAKENSIS!"=="" (
    echo.
    echo    NSIS not found on PATH or in Program Files.
    echo    Download NSIS from: https://nsis.sourceforge.io/Download
    echo    After installing, re-run this script.
    echo.
    echo    You can still run the app directly from:
    echo    dist\MTT Windows Infinite Optimizer\MTT Windows Infinite Optimizer.exe
    echo.
    pause
    exit /b 0
)

echo    Using: !MAKENSIS!

REM installer.nsi bundles the official VC++ redistributable and runs it
REM silently on targets that lack the runtime. Fetch it once into redist\
REM (git-ignored) and refuse to package it unless Microsoft's signature on it
REM checks out.
set "VCREDIST=redist\vc_redist.x64.exe"
if not exist "%VCREDIST%" (
    echo    Downloading the VC++ redistributable...
    if not exist redist md redist
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%VCREDIST%'"
)
if not exist "%VCREDIST%" (
    echo ERROR: %VCREDIST% is missing and could not be downloaded.
    echo        Download https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo        into the redist\ folder, then re-run this script.
    pause
    exit /b 1
)
powershell -NoProfile -Command "$s = Get-AuthenticodeSignature '%VCREDIST%'; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { exit 1 }"
if errorlevel 1 (
    echo ERROR: %VCREDIST% does not carry a valid Microsoft signature.
    echo        Delete it and re-run this script to download a fresh copy.
    pause
    exit /b 1
)
echo    VC++ redistributable: %VCREDIST% (Microsoft signature verified)

"!MAKENSIS!" /DAPPVERSION=%APPVERSION% /DVCREDIST=%VCREDIST% installer.nsi
echo.

if exist "%SETUPNAME%" (
    echo    Installer created successfully.
    echo    Installer: %SETUPNAME%
) else (
    echo    NSIS build had issues. Check the output above.
    pause
    exit /b 1
)
echo.

REM ===========================================================================
REM Stage 2 of 2: sign the INSTALLER. Must run AFTER makensis has produced
REM %SETUPNAME%.
REM ===========================================================================
echo [7/8] Signing the installer...
if "!SIGNING!"=="1" (
    call :sign_file "%SETUPNAME%"
    if errorlevel 1 (
        echo.
        echo ERROR: signing the installer failed - aborting the build.
        echo        %SETUPNAME% is UNSIGNED - do not ship it.
        pause
        exit /b 1
    )
) else (
    echo    Skipped - no signing credentials in the environment.
)
echo.

echo [8/8] Build finished!
echo ============================================
echo  Version:   %APPVERSION%
echo  Installer: %SETUPNAME%
if "!SIGNING!"=="1" (
    echo  Signing:   SIGNED and VERIFIED
    echo               - app exe, packaged inside the installer
    echo               - installer, %SETUPNAME%
) else (
    echo  Signing:   UNSIGNED - credentials were not set
    echo               Set MTT_SIGN_USER, MTT_SIGN_PASS, MTT_SIGN_TOTP
    echo               and re-run to produce a signed build.
)
echo  Runtime:   VC++ and Python DLLs bundled; vc_redist runs if absent
echo.
echo  REMINDER: the real test is installing on a CLEAN Windows machine
echo            with no Python or dev tools - this box already has the
echo            runtime, so a local run proves nothing about missing DLLs.
echo ============================================
pause
exit /b 0


REM ===========================================================================
REM :sign_file  <path-to-file>
REM
REM CodeSignTool signs to -output_dir_path, NOT in place, so we sign into a
REM scratch dir and copy the signed file back over the original, then verify
REM with signtool. Returns 1 on any failure.
REM
REM Secrets are expanded with !delayed! expansion and passed inside double
REM quotes: nothing is echoed, and characters such as $ & ^ %% survive intact.
REM CodeSignTool.bat uses relative paths to its bundled JDK, so it must be run
REM from its own directory (pushd).
REM ===========================================================================
:sign_file
setlocal enabledelayedexpansion
set "TARGET=%~f1"
set "TARGETNAME=%~nx1"

if not exist "!TARGET!" (
    echo    ERROR: nothing to sign - file not found: !TARGET!
    exit /b 1
)

echo    Signing: !TARGETNAME!
if exist "!SIGNTMP!" rd /s /q "!SIGNTMP!"
md "!SIGNTMP!" 2>nul
if not exist "!SIGNTMP!" (
    echo    ERROR: could not create the scratch directory !SIGNTMP!
    exit /b 1
)

pushd "!CODESIGNTOOL!"
call "!CODESIGNTOOL!\CodeSignTool.bat" sign -username="!MTT_SIGN_USER!" -password="!MTT_SIGN_PASS!" -totp_secret="!MTT_SIGN_TOTP!" -input_file_path="!TARGET!" -output_dir_path="!SIGNTMP!"
set "CST_RC=!errorlevel!"
popd

if not exist "!SIGNTMP!\!TARGETNAME!" (
    echo    ERROR: CodeSignTool produced no signed output for !TARGETNAME!
    echo           CodeSignTool exit code: !CST_RC!
    echo           See the message above, and docs/SIGNING.md for the
    echo           known credential gotchas.
    exit /b 1
)

echo    Copying the signed file back over the original...
copy /y "!SIGNTMP!\!TARGETNAME!" "!TARGET!" >nul
if errorlevel 1 (
    echo    ERROR: could not copy the signed file back to !TARGET!
    exit /b 1
)
rd /s /q "!SIGNTMP!" 2>nul

echo    Verifying signature with signtool...
"!SIGNTOOL!" verify /pa /v "!TARGET!"
if errorlevel 1 (
    echo    ERROR: signtool verification FAILED for !TARGETNAME!
    exit /b 1
)

echo    OK: !TARGETNAME! is signed and verified.
exit /b 0
