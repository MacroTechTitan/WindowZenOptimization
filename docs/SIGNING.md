# Code Signing — Working Recipe (WindowZen)

Tool: SSL.com CodeSignTool at C:\Dev\CodeSignTool
Verified working 2026-09-11. Signs as "Macro Tech Titan Inc."

## The two things that made it work (both were the 3-week blocker)
1. SINGLE QUOTES on every argument in PowerShell. The account password
   contains a `$` — double quotes make PowerShell expand it as a
   variable and corrupt the password, causing "authorization grant is
   invalid". Single quotes pass it literally.
2. TOTP secret must be the ORIGINAL base64 string from the cert page
   (contains / + =). Do NOT convert to base32 — CodeSignTool decodes the
   base64 itself. A base32-converted secret fails with "wrong 4-byte
   ending unit".

## Command
cd C:\Dev\CodeSignTool
.\CodeSignTool.bat sign -username='MacroTechTitan' -password='<ACCOUNT_PASSWORD>' -totp_secret='<BASE64_SECRET_FROM_CERT_PAGE>' -input_file_path='<FULL_PATH_TO_EXE>' -output_dir_path='C:\Dev\signed'

## Verify
& "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe" verify /pa /v "C:\Dev\signed\<file>.exe"

## Notes
- Signed file is written to C:\Dev\signed\ (original untouched)
- The base64 TOTP secret is on the SSL.com cert page under the QR code;
  it changes each time you reset the QR — use the current one.
- Cert: Macro Tech Titan Inc., order co-831l8emme56, expires 2027-08-21
