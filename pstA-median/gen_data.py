#!/usr/bin/env python3
"""Generate all input data into data/ (Python standard library only).

1-D signal  -> data/input.txt        one integer 0..4095 per line (12-bit ADC samples)
   --kind uniform : N uniform random samples (the dataset required by the topic)   [default]
   --kind sine    : slow sine + small noise + 1 % impulse spikes (shows what a median filter is for)
2-D image   -> data/image_clean.pgm  synthetic 8-bit grayscale test image (ground truth)
               data/image_noisy.pgm  same image + salt-and-pepper noise
   --from photo.jpg : use your own photo instead of the synthetic image
                      (needs Pillow, ONLY in this preparation step; the filters stay stdlib-only)

Everything is driven by one fixed seed, so the files are identical on every machine.

Examples:
  python3 gen_data.py                      # defaults: 100000 uniform samples, 256x256 image, 5 % noise
  python3 gen_data.py --kind sine
  python3 gen_data.py --img-size 128 --noise 0.10
"""
import argparse
import math
import os
import random

p = argparse.ArgumentParser()
p.add_argument("--n", type=int, default=100_000, help="number of 1-D samples")
p.add_argument("--seed", type=int, default=42)
p.add_argument("--kind", choices=["uniform", "sine"], default="uniform")
p.add_argument("--img-size", type=int, default=256, help="image width = height in pixels")
p.add_argument("--noise", type=float, default=0.05, help="salt-and-pepper probability per pixel")
p.add_argument("--from", dest="src", default=None, help="optional photo to use instead of synthetic image")
p.add_argument("--out", default="data")
a = p.parse_args()
os.makedirs(a.out, exist_ok=True)


# ---------------- 1-D signal ----------------
rng = random.Random(a.seed)
with open(os.path.join(a.out, "input.txt"), "w", newline="\n") as f:
    for i in range(a.n):
        if a.kind == "uniform":
            v = rng.randint(0, 4095)
        else:
            v = 2048 + 1500 * math.sin(2 * math.pi * i / 2000) + rng.gauss(0, 30)
            if rng.random() < 0.01:                       # impulse noise
                v = rng.choice((0, 4095))
            v = min(4095, max(0, int(round(v))))
        f.write(f"{v}\n")
print(f"data/input.txt: {a.n} samples, kind={a.kind}, seed={a.seed}")


# ---------------- 2-D image ----------------
def write_pgm(path, w, h, px):
    with open(path, "wb") as f:
        f.write(f"P5\n{w} {h}\n255\n".encode("ascii"))
        f.write(bytes(px))


def synthetic(S):
    """Gradient background, a bright disc, a dark square, stripes and a fine checkerboard.
    The fine structures (1-4 px) are smaller than the filter window on purpose: they show
    the median filter's known weakness of removing thin details."""
    px = []
    for y in range(S):
        for x in range(S):
            v = 40 + int(150 * x / (S - 1))                                   # horizontal gradient
            if (x - 0.32 * S) ** 2 + (y - 0.32 * S) ** 2 < (0.18 * S) ** 2:  # bright disc
                v = 230
            if 0.58 * S < x < 0.88 * S and 0.12 * S < y < 0.42 * S:          # dark square
                v = 25
            if y > 0.58 * S and x < 0.45 * S:                                 # diagonal stripes, 4 px
                v = 200 if ((x + y) // 4) % 2 else 60
            if y > 0.58 * S and x > 0.55 * S:                                 # checkerboard, 2 px / 1 px lines
                if y < 0.78 * S:
                    v = 220 if ((x // 2) + (y // 2)) % 2 else 30
                else:
                    v = 220 if x % 4 == 0 else 120                            # 1-px vertical lines
            px.append(v)
    return S, S, px


if a.src:
    from PIL import Image                     # preparation only; not used by the filters
    im = Image.open(a.src).convert("L")
    im.thumbnail((a.img_size, a.img_size))
    w, h = im.size
    clean = list(im.getdata())
else:
    w, h, clean = synthetic(a.img_size)

rng = random.Random(a.seed + 1)
noisy = []
for v in clean:
    r = rng.random()
    noisy.append(0 if r < a.noise / 2 else 255 if r < a.noise else v)

write_pgm(os.path.join(a.out, "image_clean.pgm"), w, h, clean)
write_pgm(os.path.join(a.out, "image_noisy.pgm"), w, h, noisy)
print(f"data/image_clean.pgm, data/image_noisy.pgm: {w}x{h}, salt-and-pepper p={a.noise}, seed={a.seed + 1}")
