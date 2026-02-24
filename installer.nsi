!include "MUI2.nsh"
!include "FileFunc.nsh"

;---------------------------------
; General
;---------------------------------
Name "SystemOptimizer Pro"
OutFile "SystemOptimizerPro_Setup_v1.0.0.exe"
InstallDir "$PROGRAMFILES64\SystemOptimizer Pro"
InstallDirRegKey HKLM "Software\SystemOptimizer Pro" "InstallDir"
RequestExecutionLevel admin
Unicode True

;---------------------------------
; Version Info
;---------------------------------
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "SystemOptimizer Pro"
VIAddVersionKey "ProductVersion" "1.0.0"
VIAddVersionKey "CompanyName" "SystemOptimizer"
VIAddVersionKey "FileDescription" "SystemOptimizer Pro Installer"
VIAddVersionKey "FileVersion" "1.0.0"
VIAddVersionKey "LegalCopyright" "Copyright SystemOptimizer"

;---------------------------------
; Interface Settings
;---------------------------------
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to SystemOptimizer Pro Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will guide you through the installation of SystemOptimizer Pro v1.0.0.$\r$\n$\r$\nSystemOptimizer Pro helps you clean temporary files, optimize your registry, and monitor system health.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN "$INSTDIR\SystemOptimizer Pro.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch SystemOptimizer Pro"

;---------------------------------
; Pages
;---------------------------------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
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
; Installer Section
;---------------------------------
Section "Install"
    SetOutPath "$INSTDIR"

    ; Copy all application files from the PyInstaller dist folder
    File /r "dist\SystemOptimizer Pro\*.*"

    ; Write registry keys for uninstaller
    WriteRegStr HKLM "Software\SystemOptimizer Pro" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro" "DisplayName" "SystemOptimizer Pro"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro" "DisplayIcon" "$INSTDIR\SystemOptimizer Pro.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro" "Publisher" "SystemOptimizer"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro" "DisplayVersion" "1.0.0"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro" "NoRepair" 1

    ; Calculate installed size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro" "EstimatedSize" "$0"

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Create Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\SystemOptimizer Pro"
    CreateShortcut "$SMPROGRAMS\SystemOptimizer Pro\SystemOptimizer Pro.lnk" "$INSTDIR\SystemOptimizer Pro.exe"
    CreateShortcut "$SMPROGRAMS\SystemOptimizer Pro\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Create Desktop shortcut
    CreateShortcut "$DESKTOP\SystemOptimizer Pro.lnk" "$INSTDIR\SystemOptimizer Pro.exe"

SectionEnd

;---------------------------------
; Uninstaller Section
;---------------------------------
Section "Uninstall"

    ; Remove application files
    RMDir /r "$INSTDIR"

    ; Remove Start Menu shortcuts
    RMDir /r "$SMPROGRAMS\SystemOptimizer Pro"

    ; Remove Desktop shortcut
    Delete "$DESKTOP\SystemOptimizer Pro.lnk"

    ; Remove registry keys
    DeleteRegKey HKLM "Software\SystemOptimizer Pro"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SystemOptimizerPro"

SectionEnd
