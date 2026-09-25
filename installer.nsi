!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

;---------------------------------
; Version — sourced from version.json, never hardcoded
;---------------------------------
; build_installer.bat passes /DAPPVERSION=x.y.z. When makensis is run by
; hand the version is parsed straight out of version.json instead, so the
; two can never drift apart.
!ifndef APPVERSION
    !searchparse /file "version.json" `"version": "` APPVERSION `"`
!endif
!ifndef APPVERSION
    !error "Could not determine the version. Check the version.json 'version' field."
!endif

!define APPNAME     "MTT Windows Infinite Optimizer"
!define PUBLISHER   "Macro Tech Titan"
!define EXENAME     "MTT Windows Infinite Optimizer.exe"
!define DISTDIR     "dist\MTT Windows Infinite Optimizer"
; Shortcut icon, relative to $INSTDIR. PyInstaller (onedir) puts --add-data
; files under _internal\, so static\branding lands here after install.
!define APPICON     "_internal\static\branding\mtt-app.ico"
!define REGUNINST   "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer"

; Official VC++ 2015-2022 x64 redistributable. build_installer.bat downloads
; it into redist\ and passes /DVCREDIST; the default covers a manual makensis.
!ifndef VCREDIST
    !define VCREDIST "redist\vc_redist.x64.exe"
!endif
!if /FileExists "${VCREDIST}"
!else
    !error "${VCREDIST} not found. Run build_installer.bat, or download https://aka.ms/vs/17/release/vc_redist.x64.exe into redist\."
!endif
; Python 3.12 is built with VS 2022; runtimes older than 14.40 get upgraded.
!define VCRT_MIN_MINOR 40

;---------------------------------
; General
;---------------------------------
Name "${APPNAME}"
OutFile "MTT_InfiniteOptimizer_Setup_v${APPVERSION}.exe"
InstallDir "$PROGRAMFILES64\${APPNAME}"
InstallDirRegKey HKLM "Software\${APPNAME}" "InstallDir"
; The app cleans system locations and needs elevation, so the installer
; (and the shortcuts it creates) must run as administrator.
RequestExecutionLevel admin
Unicode True
SetCompressor /SOLID lzma

;---------------------------------
; Version Info
;---------------------------------
VIProductVersion "${APPVERSION}.0"
VIAddVersionKey "ProductName"     "${APPNAME}"
VIAddVersionKey "ProductVersion"  "${APPVERSION}"
VIAddVersionKey "CompanyName"     "${PUBLISHER}"
VIAddVersionKey "FileDescription" "${APPNAME} Installer"
VIAddVersionKey "FileVersion"     "${APPVERSION}"
VIAddVersionKey "LegalCopyright"  "Copyright ${PUBLISHER}"

;---------------------------------
; Interface Settings
;---------------------------------
!define MUI_ABORTWARNING
!define MUI_ICON   "static\branding\mtt-installer.ico"
!define MUI_UNICON "static\branding\mtt-installer.ico"
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APPNAME} Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will guide you through the installation of ${APPNAME} v${APPVERSION}.$\r$\n$\r$\n${APPNAME} helps you clean temporary files, reclaim disk space, find large and duplicate files, review local AI model storage, optimize your internet connection, and monitor system health.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXENAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APPNAME}"

;---------------------------------
; Pages
;---------------------------------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;---------------------------------
; Languages
;---------------------------------
!insertmacro MUI_LANGUAGE "English"

;---------------------------------
; Installer Sections
;---------------------------------
; Hidden, runs first. The app also carries its own vcruntime140*.dll in
; _internal\, so this is belt-and-suspenders for a clean machine: install
; the system-wide VC++ runtime silently when it is missing or too old.
Section "-VC++ Runtime" SecVCRedist
    SetRegView 64
    ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
    ReadRegDWORD $1 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Major"
    ReadRegDWORD $2 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Minor"
    SetRegView lastused

    ${If} $0 == 1
    ${AndIf} $1 == 14
    ${AndIf} $2 >= ${VCRT_MIN_MINOR}
        DetailPrint "Visual C++ runtime 14.$2 already installed."
    ${Else}
        DetailPrint "Installing the Microsoft Visual C++ runtime..."
        InitPluginsDir
        SetOutPath "$PLUGINSDIR"
        File "/oname=vc_redist.x64.exe" "${VCREDIST}"
        ExecWait '"$PLUGINSDIR\vc_redist.x64.exe" /install /quiet /norestart' $3
        ; 0 = installed, 1638 = a newer version is already present,
        ; 3010 = installed, reboot pending (the bundled DLLs cover this run).
        ${If} $3 == 0
        ${OrIf} $3 == 1638
        ${OrIf} $3 == 3010
            DetailPrint "Visual C++ runtime ready (exit code $3)."
        ${Else}
            DetailPrint "Visual C++ runtime install failed (exit code $3)."
            MessageBox MB_OK|MB_ICONEXCLAMATION "The Microsoft Visual C++ runtime could not be installed (error $3).$\r$\n$\r$\n${APPNAME} will still be installed, but if it fails to start, install the runtime from:$\r$\nhttps://aka.ms/vs/17/release/vc_redist.x64.exe" /SD IDOK
        ${EndIf}
        Delete "$PLUGINSDIR\vc_redist.x64.exe"
    ${EndIf}
SectionEnd

Section "!${APPNAME}" SecMain
    SectionIn RO                       ; required, cannot be unticked
    SetOutPath "$INSTDIR"

    ; Everything PyInstaller produced in dist/
    File /r "${DISTDIR}\*.*"

    ; Install location
    WriteRegStr HKLM "Software\${APPNAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\${APPNAME}" "Version"    "${APPVERSION}"

    ; Add/Remove Programs registration
    WriteRegStr   HKLM "${REGUNINST}" "DisplayName"     "${APPNAME}"
    WriteRegStr   HKLM "${REGUNINST}" "DisplayVersion"  "${APPVERSION}"
    WriteRegStr   HKLM "${REGUNINST}" "Publisher"       "${PUBLISHER}"
    WriteRegStr   HKLM "${REGUNINST}" "DisplayIcon"     "$INSTDIR\${EXENAME}"
    WriteRegStr   HKLM "${REGUNINST}" "InstallLocation" "$INSTDIR"
    WriteRegStr   HKLM "${REGUNINST}" "UninstallString"       "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr   HKLM "${REGUNINST}" "QuietUninstallString"  "$\"$INSTDIR\Uninstall.exe$\" /S"
    WriteRegDWORD HKLM "${REGUNINST}" "NoModify" 1
    WriteRegDWORD HKLM "${REGUNINST}" "NoRepair" 1

    ; Installed size for Add/Remove Programs
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${REGUNINST}" "EstimatedSize" "$0"

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${EXENAME}" "" "$INSTDIR\${APPICON}" 0
    CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Desktop shortcut" SecDesktop
    CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXENAME}" "" "$INSTDIR\${APPICON}" 0
SectionEnd

;---------------------------------
; Component descriptions
;---------------------------------
LangString DESC_SecMain    ${LANG_ENGLISH} "The ${APPNAME} application and all required files. Required."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Place a shortcut to ${APPNAME} on your desktop."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}    $(DESC_SecMain)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;---------------------------------
; Uninstaller
;---------------------------------
Section "Uninstall"
    Delete "$INSTDIR\Uninstall.exe"

    ; Only recurse into the directory we actually installed into.
    RMDir /r "$INSTDIR\_internal"
    RMDir /r "$INSTDIR\templates"
    RMDir /r "$INSTDIR\static"
    Delete "$INSTDIR\*.*"
    RMDir /r "$INSTDIR"

    RMDir /r "$SMPROGRAMS\${APPNAME}"
    Delete "$DESKTOP\${APPNAME}.lnk"

    DeleteRegKey HKLM "Software\${APPNAME}"
    DeleteRegKey HKLM "${REGUNINST}"
SectionEnd
