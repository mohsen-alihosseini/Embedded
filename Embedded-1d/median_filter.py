#!/usr/bin/env python3
"""Sliding-window median filter benchmark - Python, standard library only.
Mirrors median_filter.cpp step for step.

Input : ASCII file, one integer 0..4095 per line (12-bit ADC samples).
Window: W samples, W odd (default 31), moved by one sample; one output per
        complete window (N - W + 1 values).
Median: the middle value of the sorted window (the 16th smallest for W = 31).
        Because W is odd, the median is always one of the samples: an integer.

Methods (same algorithm in both languages)
  sort      copy the window, library sort, take the middle             O(W log W) per output
  insertion sorted window maintained with hand-written binary search
            and element-shifting loops (remove outgoing, insert incoming) O(W) per output
  bisect    same sorted window, but library calls:
            bisect_left + del, insort  <->  lower_bound + erase, upper_bound + insert
  histogram running histogram (4096 bins) + moving median pointer
            (Huang, Yang & Tang 1979)

Usage
  python3 median_filter.py <method> <in.txt> <out.txt|-> [reps] [W]
One timing line per repetition is printed to stderr as key=value pairs.
"""
import resource
import sys
import time
from bisect import bisect_left, insort

METHODS = ("sort", "insertion", "bisect", "histogram")
VMAX = 4096                                   # value range 0..4095


def proc_status():
    """Current RSS, peak RSS (KiB) and thread count of this process (Linux /proc)."""
    d = {"VmRSS": -1, "VmHWM": -1, "Threads": -1}
    try:
        with open("/proc/self/status") as f:
            for line in f:
                k, _, v = line.partition(":")
                if k in d:
                    d[k] = int(v.split()[0])
    except OSError:
        pass
    return d


# ---------------------------------------------------------------------
# hand-written sorted-array helpers (used by the insertion method)
# ---------------------------------------------------------------------
def lower_bound_idx(a, n, v):
    """First position in a[0:n] whose value is >= v (binary search)."""
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
    while k + 1 < n:                          # shift left over the removed element
        srt[k] = srt[k + 1]
        k += 1
    p = lower_bound_idx(srt, n - 1, new)
    k = n - 1
    while k > p:                              # shift right to open a slot
        srt[k] = srt[k - 1]
        k -= 1
    srt[p] = new


# ---------------------------------------------------------------------
# the four methods: fill out (one median per window) and return the checksum
# ---------------------------------------------------------------------
def m_sort(x, W, out):
    cs, mid = 0, W // 2                       # mid = 15 for W = 31
    for i in range(len(x) - W + 1):
        med = sorted(x[i:i + W])[mid]         # copy window + library sort
        out.append(med)
        cs += med
    return cs


def m_insertion(x, W, out):
    ring, srt = [0] * W, [0] * W              # ring buffer (arrival order) + sorted copy
    filled = head = cs = 0
    mid = W // 2
    for v in x:
        if filled < W:                        # window not full yet
            ring[filled] = v
            insert_sorted(srt, filled, v)
            filled += 1
        else:                                 # remove oldest, insert newest
            old = ring[head]
            ring[head] = v
            head = 0 if head + 1 == W else head + 1
            replace_sorted(srt, W, old, v)
        if filled == W:
            med = srt[mid]
            out.append(med)
            cs += med
    return cs


def m_bisect(x, W, out):
    srt, cs, mid = [], 0, W // 2
    for i, v in enumerate(x):
        if i >= W:
            del srt[bisect_left(srt, x[i - W])]   # remove the sample leaving the window
        insort(srt, v)                            # insert the new sample
        if i + 1 >= W:
            med = srt[mid]
            out.append(med)
            cs += med
    return cs


def m_histogram(x, W, out):
    hist = [0] * VMAX
    rank = W // 2                             # 0-based rank of the median (15 for W = 31)
    m = lt = cs = 0                           # m: median value, lt: number of samples < m
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
        while lt > rank:                      # move pointer down
            m -= 1
            lt -= hist[m]
        while lt + hist[m] <= rank:           # move pointer up
            lt += hist[m]
            m += 1
        out.append(m)                         # now: lt <= rank < lt + hist[m]  ->  m is the median
        cs += m
    return cs


FUNCS = dict(zip(METHODS, (m_sort, m_insertion, m_bisect, m_histogram)))


def main():
    a = sys.argv
    if len(a) < 4 or a[1] not in METHODS:
        print(__doc__, file=sys.stderr)
        return 2
    method, inp, outp = a[1], a[2], a[3]
    reps = int(a[4]) if len(a) > 4 else 1
    W = int(a[5]) if len(a) > 5 else 31
    if W < 1 or W % 2 == 0:
        print("W must be odd and >= 1", file=sys.stderr)
        return 2

    rss_start = proc_status()["VmRSS"]       # interpreter + modules, before any data

    # ---- load (timed separately) ----
    t0 = time.monotonic_ns()
    with open(inp) as f:
        x = [int(t) for t in f.read().split()]
    load_ns = time.monotonic_ns() - t0
    if any(v < 0 or v >= VMAX for v in x):
        print("value out of range 0..4095", file=sys.stderr)
        return 1
    rss_load = proc_status()["VmRSS"]        # + loaded input data

    # ---- filter only (no file output, no formatting) ----
    out = []
    for r in range(reps):
        out = []
        c0, w0 = time.process_time_ns(), time.monotonic_ns()
        cs = FUNCS[method](x, W, out) if len(x) >= W else 0
        w1, c1 = time.monotonic_ns(), time.process_time_ns()
        print(f"lang=py method={method} size={W} rep={r} n_in={len(x)} "
              f"load_ns={load_ns} filter_ns={w1 - w0} filter_cpu_ns={c1 - c0} "
              f"checksum={cs} n_out={len(out)}", file=sys.stderr)

    # ---- output (not part of the filter timing) ----
    if outp != "-":
        with open(outp, "w", newline="\n") as f:
            for med in out:
                f.write(f"{med}\n")
    st = proc_status()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # Linux: KiB
    print(f"lang=py method={method} maxrss_kib={rss} rss_start_kib={rss_start} "
          f"rss_load_kib={rss_load} rss_end_kib={st['VmRSS']} threads={st['Threads']}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
