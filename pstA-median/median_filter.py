#!/usr/bin/env python3
"""Median filter benchmark program - Python, standard library only.
Mirrors median_filter.cpp step for step.

Modes
  1d : sliding window over a 1-D integer signal (0..4095), window W (default 32),
       one output per complete window (N - W + 1 values).
       Even W -> median = mean of the two middle values; kept as s = 2*median and
       printed as s//2 + ".0" / ".5".
  2d : k x k window (k odd, default 5) over an 8-bit grayscale PGM image (P5).
       Borders: edge replication (clamp), so the output has the same size as the input.

Methods (same algorithm in both languages)
  sort      copy the window, library sort, take the middle             O(n log n) per output
  insertion sorted window maintained with hand-written binary search
            and element-shifting loops (remove outgoing, insert incoming) O(n) per changed value
  bisect    same sorted window, but library calls:
            bisect_left + del, insort  <->  lower_bound + erase, upper_bound + insert
  histogram running histogram + moving median pointer (Huang, Yang & Tang 1979)
            1d: 4096 bins, 2d: 256 bins

Usage
  python3 median_filter.py 1d <method> <in.txt> <out.txt|-> [reps] [W]
  python3 median_filter.py 2d <method> <in.pgm> <out.pgm|-> [reps] [k]
One timing line per repetition is printed to stderr as key=value pairs.
"""
import resource
import sys
import time
from bisect import bisect_left, insort

METHODS = ("sort", "insertion", "bisect", "histogram")


# =====================================================================
# shared helpers (hand-written sorted-array operations)
# =====================================================================
def lower_bound_idx(a, n, v):
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return lo


def insert_sorted(srt, filled, v):
    """Insert v into srt[0:filled] (sorted); srt has room for one more."""
    p = lower_bound_idx(srt, filled, v)
    k = filled
    while k > p:
        srt[k] = srt[k - 1]
        k -= 1
    srt[p] = v


def replace_sorted(srt, n, old, new):
    """Remove one occurrence of old from srt[0:n] and insert new; keeps it sorted."""
    k = lower_bound_idx(srt, n, old)
    while k + 1 < n:                     # shift left over the removed element
        srt[k] = srt[k + 1]
        k += 1
    p = lower_bound_idx(srt, n - 1, new)
    k = n - 1
    while k > p:                         # shift right to open a slot
        srt[k] = srt[k - 1]
        k -= 1
    srt[p] = new


# =====================================================================
# 1-D methods: fill out (list of 2*median) and return checksum
# =====================================================================
def s1_sort(x, W, out):
    cs, half, even = 0, W // 2, W % 2 == 0
    for i in range(len(x) - W + 1):
        buf = sorted(x[i:i + W])
        s = buf[half - 1] + buf[half] if even else 2 * buf[half]
        out.append(s)
        cs += s
    return cs


def s1_insertion(x, W, out):
    ring, srt = [0] * W, [0] * W
    filled = head = cs = 0
    half, even = W // 2, W % 2 == 0
    for v in x:
        if filled < W:
            ring[filled] = v
            insert_sorted(srt, filled, v)
            filled += 1
        else:
            old = ring[head]
            ring[head] = v
            head = 0 if head + 1 == W else head + 1
            replace_sorted(srt, W, old, v)
        if filled == W:
            s = srt[half - 1] + srt[half] if even else 2 * srt[half]
            out.append(s)
            cs += s
    return cs


def s1_bisect(x, W, out):
    srt, cs = [], 0
    half, even = W // 2, W % 2 == 0
    for i, v in enumerate(x):
        if i >= W:
            del srt[bisect_left(srt, x[i - W])]
        insort(srt, v)
        if i + 1 >= W:
            s = srt[half - 1] + srt[half] if even else 2 * srt[half]
            out.append(s)
            cs += s
    return cs


def s1_histogram(x, W, out):
    hist = [0] * 4096
    even = W % 2 == 0
    rank = W // 2 - 1 if even else W // 2     # 0-based rank of the (lower) middle value
    m = lt = cs = 0                            # m: median value, lt: #samples < m
    for i, v in enumerate(x):
        hist[v] += 1
        if v < m:
            lt += 1
        if i >= W:
            o = x[i - W]
            hist[o] -= 1
            if o < m:
                lt -= 1
        if i + 1 < W:
            continue
        while lt > rank:
            m -= 1
            lt -= hist[m]
        while lt + hist[m] <= rank:
            lt += hist[m]
            m += 1
        hi = m
        if even and lt + hist[m] <= rank + 1:  # upper middle lies in a later bin
            hi = m + 1
            while hist[hi] == 0:
                hi += 1
        s = m + hi if even else 2 * m
        out.append(s)
        cs += s
    return cs


# =====================================================================
# 2-D methods: img is a flat row-major list, returns (out list, checksum)
# =====================================================================
def pad_clamp(img, w, h, r):
    """Edge-replicated copy with r extra pixels on every side."""
    P = []
    for yy in range(-r, h + r):
        y = 0 if yy < 0 else h - 1 if yy >= h else yy
        row = img[y * w:(y + 1) * w]
        P += [row[0]] * r + row + [row[-1]] * r
    return P, w + 2 * r


def s2_sort(img, w, h, k):
    P, pw = pad_clamp(img, w, h, k // 2)
    mid = (k * k) // 2
    out = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            buf = []
            base = y * pw + x
            for dy in range(k):
                s = base + dy * pw
                buf += P[s:s + k]
            buf.sort()
            out[y * w + x] = buf[mid]
    return out


def s2_insertion(img, w, h, k):
    P, pw = pad_clamp(img, w, h, k // 2)
    n, mid = k * k, (k * k) // 2
    srt = [0] * n
    out = [0] * (w * h)
    for y in range(h):
        filled = 0                                       # first window of the row
        for dy in range(k):
            base = (y + dy) * pw
            for dx in range(k):
                insert_sorted(srt, filled, P[base + dx])
                filled += 1
        out[y * w] = srt[mid]
        for x in range(1, w):                            # slide right: column out, column in
            for dy in range(k):
                base = (y + dy) * pw
                replace_sorted(srt, n, P[base + x - 1], P[base + x + k - 1])
            out[y * w + x] = srt[mid]
    return out


def s2_bisect(img, w, h, k):
    P, pw = pad_clamp(img, w, h, k // 2)
    mid = (k * k) // 2
    out = [0] * (w * h)
    for y in range(h):
        srt = []
        for dy in range(k):
            base = (y + dy) * pw
            for dx in range(k):
                insort(srt, P[base + dx])
        out[y * w] = srt[mid]
        for x in range(1, w):
            for dy in range(k):
                base = (y + dy) * pw
                del srt[bisect_left(srt, P[base + x - 1])]
                insort(srt, P[base + x + k - 1])
            out[y * w + x] = srt[mid]
    return out


def s2_histogram(img, w, h, k):
    """Huang, Yang & Tang (1979): per row, update the histogram column by column."""
    P, pw = pad_clamp(img, w, h, k // 2)
    rank = (k * k) // 2
    out = [0] * (w * h)
    for y in range(h):
        hist = [0] * 256
        for dy in range(k):
            base = (y + dy) * pw
            for dx in range(k):
                hist[P[base + dx]] += 1
        m = lt = 0
        while lt + hist[m] <= rank:
            lt += hist[m]
            m += 1
        out[y * w] = m
        for x in range(1, w):
            for dy in range(k):
                base = (y + dy) * pw
                o = P[base + x - 1]
                hist[o] -= 1
                if o < m:
                    lt -= 1
                v = P[base + x + k - 1]
                hist[v] += 1
                if v < m:
                    lt += 1
            while lt > rank:
                m -= 1
                lt -= hist[m]
            while lt + hist[m] <= rank:
                lt += hist[m]
                m += 1
            out[y * w + x] = m
    return out


F1 = dict(zip(METHODS, (s1_sort, s1_insertion, s1_bisect, s1_histogram)))
F2 = dict(zip(METHODS, (s2_sort, s2_insertion, s2_bisect, s2_histogram)))


# =====================================================================
# PGM (P5, maxval 255) I/O
# =====================================================================
def read_pgm(path):
    data = open(path, "rb").read()
    tok, pos = [], 0
    while len(tok) < 4:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while data[pos:pos + 1] not in (b"\n", b""):
                pos += 1
            continue
        start = pos
        while not data[pos:pos + 1].isspace():
            pos += 1
        tok.append(data[start:pos])
    pos += 1                                        # single whitespace after maxval
    if tok[0] != b"P5" or int(tok[3]) != 255:
        raise ValueError("only binary 8-bit PGM (P5, maxval 255) is supported")
    w, h = int(tok[1]), int(tok[2])
    return w, h, list(data[pos:pos + w * h])


def write_pgm(path, w, h, px):
    with open(path, "wb") as f:
        f.write(f"P5\n{w} {h}\n255\n".encode("ascii"))
        f.write(bytes(px))


# =====================================================================
def main():
    a = sys.argv
    if len(a) < 5 or a[1] not in ("1d", "2d") or a[2] not in METHODS:
        print(__doc__, file=sys.stderr)
        return 2
    mode, method, inp, outp = a[1], a[2], a[3], a[4]
    reps = int(a[5]) if len(a) > 5 else 1
    size = int(a[6]) if len(a) > 6 else (32 if mode == "1d" else 5)

    # ---- load (timed separately) ----
    t0 = time.monotonic_ns()
    if mode == "1d":
        with open(inp) as f:
            x = [int(t) for t in f.read().split()]
        if any(v < 0 or v > 4095 for v in x):
            print("value out of range 0..4095", file=sys.stderr)
            return 1
        n_in = len(x)
    else:
        w, h, img = read_pgm(inp)
        n_in = w * h
        if size < 1 or size % 2 == 0:
            print("k must be odd", file=sys.stderr)
            return 2
    load_ns = time.monotonic_ns() - t0

    # ---- filter only (no file output, no formatting) ----
    out = []
    for r in range(reps):
        c0, w0 = time.process_time_ns(), time.monotonic_ns()
        if mode == "1d":
            out = []
            cs = F1[method](x, size, out) if len(x) >= size else 0
        else:
            out = F2[method](img, w, h, size)
            cs = sum(out)            # checksum proves the work was done (same in C++)
        w1, c1 = time.monotonic_ns(), time.process_time_ns()
        print(f"lang=py mode={mode} method={method} size={size} rep={r} n_in={n_in} "
              f"load_ns={load_ns} filter_ns={w1 - w0} filter_cpu_ns={c1 - c0} "
              f"checksum={cs} n_out={len(out)}", file=sys.stderr)

    # ---- output (not part of the filter timing) ----
    if outp != "-":
        if mode == "1d":
            with open(outp, "w", newline="\n") as f:
                for s in out:
                    f.write(f"{s // 2}.{'5' if s % 2 else '0'}\n")
        else:
            write_pgm(outp, w, h, out)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # Linux: KiB
    print(f"lang=py mode={mode} method={method} maxrss_kib={rss}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
