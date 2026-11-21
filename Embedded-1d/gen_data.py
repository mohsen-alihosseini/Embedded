#!/usr/bin/env python3
"""Generate the benchmark input data/input.txt (Python standard library only).

One integer 0..4095 per line (12-bit ADC samples), LF line endings.
   --kind uniform : N uniform random samples (the dataset used in the thesis)   [default]
   --kind sine    : slow sine + small noise + 1 % impulse spikes (optional experiment)
A fixed seed makes the file identical on every machine.

Examples:
  python3 gen_data.py                 # 100000 uniform samples, seed 42
  python3 gen_data.py --kind sine
"""
import argparse
import math
import os
import random

p = argparse.ArgumentParser()
p.add_argument("--n", type=int, default=100_000, help="number of samples")
p.add_argument("--seed", type=int, default=42)
p.add_argument("--kind", choices=["uniform", "sine"], default="uniform")
p.add_argument("--out", default="data/input.txt")
a = p.parse_args()
os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

rng = random.Random(a.seed)
with open(a.out, "w", newline="\n") as f:
    for i in range(a.n):
        if a.kind == "uniform":
            v = rng.randint(0, 4095)
        else:
            v = 2048 + 1500 * math.sin(2 * math.pi * i / 2000) + rng.gauss(0, 30)
            if rng.random() < 0.01:                       # impulse noise
                v = rng.choice((0, 4095))
            v = min(4095, max(0, int(round(v))))
        f.write(f"{v}\n")
print(f"{a.out}: {a.n} samples, kind={a.kind}, seed={a.seed}")
