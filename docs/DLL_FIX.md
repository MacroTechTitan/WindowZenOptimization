# Fix: install fails on clean machine — missing DLL

Symptom: installer fails on a clean Windows machine (no Python/dev tools)
with a missing DLL error. Works on dev box because the runtime is already
present. This blocks ALL users. Keep onedir (not onefile — onefile
worsens SmartScreen/AV false-positives for an elevated system tool).

## Likely cause
PyInstaller is not bundling the Visual C++ runtime (vcruntime140.dll /
vcruntime140_1.dll) and/or python3.dll that the app needs at runtime.

## Fix in build_installer.bat / PyInstaller
1. Ensure PyInstaller bundles the VC++ runtime. Add these hidden imports
   / binaries as needed and confirm they land in dist:
   - vcruntime140.dll, vcruntime140_1.dll (from the system or the Python
     install's DLLs)
   - python3.dll and python312.dll (the Python shared libs)
   Use --add-binary to force-include any that PyInstaller misses, sourcing
   them from the Python install (C:\Users\macro\AppData\Local\Programs\
   Python\Python312\ and its DLLs subdir) — NOT hardcoded to that path;
   resolve dynamically so it works on any build machine.
2. After build, verify the dist folder contains the VC++ runtime DLLs and
   python3*.dll. Print a check in the build output listing which runtime
   DLLs shipped.
3. Belt-and-suspenders: have installer.nsi check for the VC++ runtime on
   the target machine and, if absent, either bundle+run the official
   VC++ redistributable installer (vc_redist.x64.exe) silently, or warn
   the user with a download link. Bundling vc_redist is the robust option
   for a consumer installer.

## Also (fold in)
- Remove the now-unused /admin/api/check-remote-manifest endpoint in
  routes/admin.py:212 (points at the dead update system).

## Verify
- python -c "import app" clean.
- Rebuild, confirm the runtime DLLs are in dist and the build still signs
  + verifies.
- The real test is a CLEAN machine install — note in output that this
  must be re-tested on a machine without Python.

Commit the DLL fix and the endpoint removal separately.
