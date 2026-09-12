# Task: Wire code signing into build_installer.bat (two-stage)

Working recipe is in docs/SIGNING.md. Use it exactly. Key facts:
- Signing tool: C:\Dev\CodeSignTool\CodeSignTool.bat
- Command form (single quotes, base64 secret as-is):
  CodeSignTool.bat sign -username=USER -password=PASS -totp_secret=SECRET
    -input_file_path=FILE -output_dir_path=OUTDIR
- Verify tool: C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe

## Secrets handling (CRITICAL)
Do NOT hardcode username/password/secret in the .bat — this repo is
public. Read them from environment variables the user sets locally:
  MTT_SIGN_USER, MTT_SIGN_PASS, MTT_SIGN_TOTP
If any is unset, the script should PRINT a clear message and SKIP signing
(still produce the unsigned build) rather than fail the whole build.
Add a .gitignore entry if any secret file is introduced (prefer env vars,
no file).

## Two-stage signing — correct order matters
The app exe must be signed BEFORE NSIS packages it; the installer signed
AFTER NSIS builds it.

Modify build_installer.bat so the flow is:
1. PyInstaller builds dist\MTT Windows Infinite Optimizer\...exe (as now)
2. NEW: sign the inner app exe:
   dist\MTT Windows Infinite Optimizer\MTT Windows Infinite Optimizer.exe
   - CodeSignTool writes signed output to a temp dir, then copy it back
     over the original in dist\ (CodeSignTool signs to output_dir_path,
     doesn't sign in place — handle the copy-back).
   - Verify with signtool; abort build on verify failure.
3. NSIS packages the (now-signed) app into the installer (as now)
4. NEW: sign the installer exe MTT_InfiniteOptimizer_Setup_vX.Y.Z.exe
   the same way (sign to temp, copy back, verify).
5. Print a clear SIGNED / verified summary at the end.

## Guardrails
- If env vars are missing: skip signing, build still succeeds unsigned,
  print how to set them.
- Never echo the password or secret to the console.
- Keep the existing version-from-version.json logic intact.
- Don't break the existing unsigned build path.

## After implementing
Show the user the exact commands to set the three env vars in their
shell (PowerShell setx or $env:), and how to run one signed build.
