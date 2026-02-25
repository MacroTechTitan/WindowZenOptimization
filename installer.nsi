!include "MUI2.nsh"
!include "FileFunc.nsh"

;---------------------------------
; General
;---------------------------------
Name "MTT Windows Infinite Optimizer"
OutFile "MTT_InfiniteOptimizer_Setup_v1.0.0.exe"
InstallDir "$PROGRAMFILES64\MTT Windows Infinite Optimizer"
InstallDirRegKey HKLM "Software\MTT Windows Infinite Optimizer" "InstallDir"
RequestExecutionLevel admin
Unicode True

;---------------------------------
; Version Info
;---------------------------------
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "MTT Windows Infinite Optimizer"
VIAddVersionKey "ProductVersion" "1.0.0"
VIAddVersionKey "CompanyName" "Macro Tech Titan"
VIAddVersionKey "FileDescription" "MTT Windows Infinite Optimizer Installer"
VIAddVersionKey "FileVersion" "1.0.0"
VIAddVersionKey "LegalCopyright" "Copyright Macro Tech Titan"

;---------------------------------
; Interface Settings
;---------------------------------
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to MTT Windows Infinite Optimizer Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will guide you through the installation of MTT Windows Infinite Optimizer v1.0.0.$\r$\n$\r$\nMTT Windows Infinite Optimizer helps you clean temporary files, optimize your registry, and monitor system health.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN "$INSTDIR\MTT Windows Infinite Optimizer.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch MTT Windows Infinite Optimizer"

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
    File /r "dist\MTT Windows Infinite Optimizer\*.*"

    ; Write registry keys for uninstaller
    WriteRegStr HKLM "Software\MTT Windows Infinite Optimizer" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer" "DisplayName" "MTT Windows Infinite Optimizer"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer" "DisplayIcon" "$INSTDIR\MTT Windows Infinite Optimizer.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer" "Publisher" "Macro Tech Titan"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer" "DisplayVersion" "1.0.0"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer" "NoRepair" 1

    ; Calculate installed size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer" "EstimatedSize" "$0"

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Create Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\MTT Windows Infinite Optimizer"
    CreateShortcut "$SMPROGRAMS\MTT Windows Infinite Optimizer\MTT Windows Infinite Optimizer.lnk" "$INSTDIR\MTT Windows Infinite Optimizer.exe"
    CreateShortcut "$SMPROGRAMS\MTT Windows Infinite Optimizer\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Create Desktop shortcut
    CreateShortcut "$DESKTOP\MTT Windows Infinite Optimizer.lnk" "$INSTDIR\MTT Windows Infinite Optimizer.exe"

SectionEnd

;---------------------------------
; Uninstaller Section
;---------------------------------
Section "Uninstall"

    ; Remove application files
    RMDir /r "$INSTDIR"

    ; Remove Start Menu shortcuts
    RMDir /r "$SMPROGRAMS\MTT Windows Infinite Optimizer"

    ; Remove Desktop shortcut
    Delete "$DESKTOP\MTT Windows Infinite Optimizer.lnk"

    ; Remove registry keys
    DeleteRegKey HKLM "Software\MTT Windows Infinite Optimizer"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MTTInfiniteOptimizer"

SectionEnd
