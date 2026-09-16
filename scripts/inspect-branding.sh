#!/usr/bin/env bash
# Print pixel dimensions of the branding images and the sizes embedded in
# each .ico, so template/installer wiring can be checked against the assets.
set -euo pipefail

DIR="${1:-static/branding}"
echo "Inspecting branding assets in: $DIR"

python - "$DIR" <<'PY'
import os, struct, sys

d = sys.argv[1]
try:
    from PIL import Image
except ImportError:
    Image = None
    print("(Pillow not installed - image dimensions skipped)")

for name in sorted(os.listdir(d)):
    path = os.path.join(d, name)
    size = os.path.getsize(path)
    if name.endswith(".ico"):
        with open(path, "rb") as f:
            _, kind, count = struct.unpack("<HHH", f.read(6))
            dims = []
            for _ in range(count):
                w, h = struct.unpack("<BB", f.read(2))
                f.read(14)
                dims.append(f"{w or 256}x{h or 256}")
        print(f"{name:24} {size:>9} B  ico type={kind} sizes={','.join(dims)}")
    elif name.endswith(".png"):
        # IHDR: width, height, bit depth, colour type (6 = RGBA, 2 = RGB).
        with open(path, "rb") as f:
            head = f.read(26)
        w, h = struct.unpack(">II", head[16:24])
        print(f"{name:24} {size:>9} B  {w}x{h} depth={head[24]} colortype={head[25]}")
    elif Image is not None:
        with Image.open(path) as im:
            print(f"{name:24} {size:>9} B  {im.width}x{im.height} {im.mode}")
    else:
        print(f"{name:24} {size:>9} B")
PY
