#!/usr/bin/env python3
"""Summarise one results/raw_* folder (standard library; plots only if matplotlib exists).
Usage: python3 scripts/analyze.py results/raw_YYYYMMDD_HHMMSS

Writes into that folder:
  summary.csv  median, quartiles, IQR, min, max per source/metric/method/lang
               (times, CPU usage, threads, RAM at start / after loading / end / peak)
  ratio.csv    Python / C++ ratio of the medians
  box_filter_ms.png, box_wall_s.png   boxplots, if matplotlib is installed
Also checks that every run produced the same checksum.
"""
import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ORDER = ["sort", "insertion", "bisect", "histogram"]


def parse(path):
    p = Path(path)
    if not p.exists():
        return []
    return [dict(kv.split("=", 1) for kv in line.split())
            for line in p.read_text().splitlines() if "lang=" in line]


def summary(v):
    q = st.quantiles(v, n=4, method="inclusive") if len(v) >= 2 else [v[0]] * 3
    return dict(n=len(v), median=st.median(v), q1=q[0], q3=q[2], iqr=q[2] - q[0],
                min=min(v), max=max(v))


d = Path(sys.argv[1])
g = defaultdict(list)          # (source, metric, method, lang) -> values
for r in parse(d / "e2e.txt"):
    for m in ("wall_s", "user_s", "sys_s", "maxrss_kib", "cpu_pct", "ctx_vol", "ctx_invol"):
        if m in r:
            g[("e2e", m, r["method"], r["lang"])].append(float(r[m].rstrip("%")))
for r in parse(d / "inproc_single.txt"):
    if "filter_ns" in r:
        g[("single", "load_ms", r["method"], r["lang"])].append(int(r["load_ns"]) / 1e6)
        g[("single", "filter_ms", r["method"], r["lang"])].append(int(r["filter_ns"]) / 1e6)
        g[("single", "filter_cpu_ms", r["method"], r["lang"])].append(int(r["filter_cpu_ns"]) / 1e6)
        g[("single", "filter_cpu_pct", r["method"], r["lang"])].append(
            100 * int(r["filter_cpu_ns"]) / max(1, int(r["filter_ns"])))
    if "rss_start_kib" in r:                 # memory line of the same process
        for m in ("rss_start_kib", "rss_load_kib", "rss_end_kib", "threads"):
            g[("single", m, r["method"], r["lang"])].append(float(r[m]))
for r in parse(d / "inproc_reps.txt"):
    if "filter_ns" in r:
        tag = "rep0_ms" if r["rep"] == "0" else "rep1plus_ms"
        g[("repeated", tag, r["method"], r["lang"])].append(int(r["filter_ns"]) / 1e6)

checks = {r["checksum"] for f in ("inproc_single.txt", "inproc_reps.txt")
          for r in parse(d / f) if "checksum" in r}
print("checksum:", checks, "OK" if len(checks) == 1 else "ERROR - results differ!")


def sortkey(k):
    return (k[0], k[1], ORDER.index(k[2]) if k[2] in ORDER else 9, k[3])


with open(d / "summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["source", "metric", "method", "lang", "n", "median", "q1", "q3", "iqr", "min", "max"])
    print(f"\n{'source':8} {'metric':13} {'method':9} {'lang':4} {'n':>3} {'median':>11} {'IQR':>9}")
    for k in sorted(g, key=sortkey):
        s = summary(g[k])
        w.writerow([*k, s["n"], s["median"], s["q1"], s["q3"], s["iqr"], s["min"], s["max"]])
        if k[1] in ("filter_ms", "wall_s", "maxrss_kib", "load_ms", "cpu_pct", "filter_cpu_pct",
                    "rss_start_kib", "rss_load_kib", "threads"):
            print(f"{k[0]:8} {k[1]:13} {k[2]:9} {k[3]:4} {s['n']:>3} {s['median']:>11.2f} {s['iqr']:>9.2f}")

with open(d / "ratio.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["source", "metric", "method", "py_over_cpp"])
    print("\nPython / C++ (ratio of medians)")
    for (src, met) in sorted({k[:2] for k in g}):
        line = []
        for m in ORDER:
            a, b = g.get((src, met, m, "py")), g.get((src, met, m, "cpp"))
            if a and b and st.median(b) > 0:
                ratio = st.median(a) / st.median(b)
                w.writerow([src, met, m, f"{ratio:.2f}"])
                line.append(f"{m}={ratio:.1f}x")
        print(f"  {src:8} {met:13} " + "  ".join(line))

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for src, met, label in (("single", "filter_ms", "filter-only time [ms]"),
                            ("e2e", "wall_s", "end-to-end wall time [s]")):
        fig, axs = plt.subplots(1, 2, figsize=(9, 3.4))
        for ax, lang, name in zip(axs, ("cpp", "py"), ("C++ (g++ -O2)", "Python (CPython)")):
            ax.boxplot([g.get((src, met, m, lang), [0]) for m in ORDER])
            ax.set_xticks(range(1, 5), ORDER)
            ax.set_title(name)
            ax.set_ylabel(label)
        fig.suptitle(label)
        fig.tight_layout()
        fig.savefig(d / f"box_{met}.png", dpi=150)
        plt.close(fig)
    print("\nboxplots written")
except ImportError:
    print("\n(matplotlib not installed: plots skipped)")
print(f"wrote {d / 'summary.csv'} and {d / 'ratio.csv'}")
