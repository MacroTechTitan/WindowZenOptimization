#!/usr/bin/env bash
# Decode a PNG without Pillow and report: whether it has a transparent
# background, the corner pixel colour, and the bounding box of "ink"
# (pixels that differ from the corner colour). Used to size the CSS crop of
# the square branding logo down to its wordmark band.
# Usage: bash scripts/measure-logo.sh <png-path>
set -euo pipefail

PNG="${1:?usage: measure-logo.sh <png-path>}"
echo "Measuring $PNG"

python - "$PNG" <<'PY'
import sys, zlib, struct

path = sys.argv[1]
data = open(path, "rb").read()
pos, idat = 8, b""
while pos < len(data):
    length, ctype = struct.unpack(">I4s", data[pos:pos+8])
    chunk = data[pos+8:pos+8+length]
    if ctype == b"IHDR":
        w, h, depth, color = struct.unpack(">IIBB", chunk[:10])
    elif ctype == b"IDAT":
        idat += chunk
    pos += length + 12

if depth != 8 or color != 6:
    sys.exit(f"expected 8-bit RGBA, got depth={depth} colortype={color}")

raw = zlib.decompress(idat)
stride = w * 4
rows, prev = [], bytearray(stride)
p = 0
for _ in range(h):
    f = raw[p]; p += 1
    line = bytearray(raw[p:p+stride]); p += stride
    for i in range(stride):
        a = line[i-4] if i >= 4 else 0
        b = prev[i]
        c = prev[i-4] if i >= 4 else 0
        if f == 1:   line[i] = (line[i] + a) & 0xFF
        elif f == 2: line[i] = (line[i] + b) & 0xFF
        elif f == 3: line[i] = (line[i] + (a + b) // 2) & 0xFF
        elif f == 4:
            pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
            pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            line[i] = (line[i] + pred) & 0xFF
    rows.append(line)
    prev = line

corner = tuple(rows[0][0:4])
print(f"size={w}x{h} corner_pixel(RGBA)={corner}")
print("background:", "transparent" if corner[3] == 0 else f"OPAQUE {corner[:3]}")

def ink(px):
    # Anything visibly different from the background counts as ink.
    if corner[3] == 0:
        return px[3] > 24
    return px[3] > 24 and max(abs(px[i] - corner[i]) for i in range(3)) > 24

minx, miny, maxx, maxy = w, h, -1, -1
band = []
for y in range(h):
    row = rows[y]
    found = False
    for x in range(w):
        if ink(row[x*4:x*4+4]):
            found = True
            minx, maxx = min(minx, x), max(maxx, x)
    if found:
        miny, maxy = (y if miny == h else miny), y
        band.append(y)

print(f"ink bbox: x {minx}..{maxx}  y {miny}..{maxy}")
# Report row occupancy so a gap (wordmark vs stray fragment) is visible.
gaps, run = [], None
for y in range(h):
    if y in band:
        if run is None: run = y
    elif run is not None:
        gaps.append((run, y - 1)); run = None
if run is not None: gaps.append((run, h - 1))
print("ink row bands:", gaps)
PY
