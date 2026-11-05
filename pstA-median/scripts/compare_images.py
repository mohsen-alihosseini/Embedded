#!/usr/bin/env python3
"""Visual and numerical check of the 2-D results (standard library only).
Usage: python3 scripts/compare_images.py [results/img]

Reads data/image_clean.pgm, data/image_noisy.pgm and results/img/out_<lang>_<method>.pgm
(written by `make test`), then:
  * prints a table: identical to the C++ sort result?  pixels differing,  MSE and PSNR vs. the clean image
  * writes PNGs you can open anywhere:
      results/img/montage.png  clean | noisy | filtered (Python) | filtered (C++) | |Py - C++| x 50
      results/img/zoom.png     same, 4x enlarged crop of the fine-detail area
      results/img/<each output>.png
"""
import math
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from median_filter import read_pgm   # noqa: E402

ORDER = ["sort", "insertion", "bisect", "histogram"]
d = Path(sys.argv[1] if len(sys.argv) > 1 else "results/img")


def write_png(path, w, h, px):
    raw = b"".join(b"\x00" + bytes(px[y * w:(y + 1) * w]) for y in range(h))

    def chunk(t, data):
        return (struct.pack(">I", len(data)) + t + data
                + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n"
                           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def mse(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)


def psnr(a, b):
    e = mse(a, b)
    return float("inf") if e == 0 else 10 * math.log10(255 ** 2 / e)


def montage(tiles, w, h, gap=6):
    W = len(tiles) * w + (len(tiles) - 1) * gap
    out = [255] * (W * h)
    for i, t in enumerate(tiles):
        x0 = i * (w + gap)
        for y in range(h):
            out[y * W + x0:y * W + x0 + w] = t[y * w:(y + 1) * w]
    return out, W, h


def crop_zoom(px, w, x0, y0, cw, ch, z):
    out = []
    for y in range(ch * z):
        row = px[(y0 + y // z) * w + x0:(y0 + y // z) * w + x0 + cw]
        out += [v for v in row for _ in range(z)]
    return out


w, h, clean = read_pgm("data/image_clean.pgm")
_, _, noisy = read_pgm("data/image_noisy.pgm")
outs = {}
for lang in ("py", "cpp"):
    for m in ORDER:
        p = d / f"out_{lang}_{m}.pgm"
        if p.exists():
            outs[(lang, m)] = read_pgm(p)[2]
            write_png(d / f"out_{lang}_{m}.png", w, h, outs[(lang, m)])
if not outs:
    sys.exit(f"no out_*.pgm in {d} - run `make test` first")
ref = outs.get(("cpp", "sort")) or next(iter(outs.values()))

# Regions of the synthetic image: upper part = large smooth shapes,
# lower part = stripes / checkerboard / 1-px lines (details smaller than the window).
split = int(0.58 * h) * w


def region_psnr(px):
    return (psnr(px, clean), psnr(px[:split], clean[:split]), psnr(px[split:], clean[split:]))


print(f"image {w}x{h}   PSNR vs. clean image in dB (higher = closer to the original)")
print(f"{'':22} {'= ref':>6} {'diff px':>8} {'whole':>7} {'smooth':>7} {'detail':>7}")
pw_, ps_, pd_ = region_psnr(noisy)
print(f"{'noisy (no filter)':22} {'':>6} {'':>8} {pw_:7.2f} {ps_:7.2f} {pd_:7.2f}")
for (lang, m), px in outs.items():
    diff = sum(1 for a, b in zip(px, ref) if a != b)
    pw_, ps_, pd_ = region_psnr(px)
    print(f"{lang + ' ' + m:22} {'yes' if diff == 0 else 'NO':>6} {diff:>8} {pw_:7.2f} {ps_:7.2f} {pd_:7.2f}")
print("smooth = upper 58 % of the image, detail = lower part with structures thinner than the window")

py = outs.get(("py", "histogram")) or outs.get(("py", "sort")) or ref
cp = outs.get(("cpp", "histogram")) or ref
absdiff = [min(255, abs(a - b) * 50) for a, b in zip(py, cp)]
m_px, MW, MH = montage([clean, noisy, py, cp, absdiff], w, h)
write_png(d / "montage.png", MW, MH, m_px)

# zoom on the fine-detail region (stripes / checkerboard / 1-px lines, lower part of the image)
cw = ch = max(16, w // 4)
x0, y0 = min(w - cw, int(0.55 * w)), min(h - ch, int(0.66 * h))
z = 4
tiles = [crop_zoom(t, w, x0, y0, cw, ch, z) for t in (clean, noisy, py, cp)]
z_px, ZW, ZH = montage(tiles, cw * z, ch * z)
write_png(d / "zoom.png", ZW, ZH, z_px)
print(f"\nwrote {d / 'montage.png'}  (clean | noisy | Python | C++ | |Py-C++| x 50)")
print(f"wrote {d / 'zoom.png'}     (4x crop at x={x0}, y={y0}: clean | noisy | Python | C++)")
