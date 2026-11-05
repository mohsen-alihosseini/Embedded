# PStA Embedded Linux – Topic 03 (variant): C++ vs. Python for median filters

Research question: How do equivalent C++ and Python implementations of four median-filter
methods differ in execution time and memory demand on a Raspberry Pi 1 B+, for a 1-D signal
and a 2-D image, and how does the choice of algorithm change the size of the language gap?

Target: Raspberry Pi 1 B+ (ARM1176JZF-S, ARMv6, 700 MHz, single core, 512 MB), Raspberry Pi OS Lite.

## Files
| file | what it does |
|---|---|
| `gen_data.py` | writes `data/input.txt` (100,000 ints 0..4095, seed 42) and `data/image_clean.pgm` / `data/image_noisy.pgm` (256×256, 5 % salt-and-pepper) |
| `median_filter.py` | **one** Python program: 4 methods × 1-D and 2-D (standard library only) |
| `median_filter.cpp` | **one** C++17 program: the same 4 methods × 1-D and 2-D |
| `tests/run_tests.sh` | correctness: hand-calculated cases, brute-force reference, all 8 programs identical |
| `scripts/bench.sh` | performance recording (end-to-end + filter-only + repeated runs) |
| `scripts/analyze.py` | median / IQR / min / max, Python÷C++ ratios, boxplots |
| `scripts/compare_images.py` | visual check (PNG montage + 4× zoom) and PSNR vs. the clean image |

## Command line
```
python3 median_filter.py   1d <method> data/input.txt      <out.txt|-> [reps] [W=32]
python3 median_filter.py   2d <method> data/image_noisy.pgm <out.pgm|-> [reps] [k=5]
./build/median_filter      (same arguments)
method = sort | insertion | bisect | histogram
```

## The four methods (identical output, different way of getting it)
| method | idea | what it shows |
|---|---|---|
| `sort` | copy the window, library sort, take the middle | Python's `sorted()` runs in C → small gap |
| `insertion` | keep the window sorted; hand-written binary search + shifting loops | pure interpreter overhead → large gap |
| `bisect` | same as insertion but with library calls (`bisect`/`insort` ↔ `lower_bound`/`insert`/`erase`) | same algorithm, work moved into C |
| `histogram` | running histogram + moving median pointer (Huang, Yang & Tang 1979); 1-D: 4096 bins, 2-D: 256 bins | best algorithm in theory; result depends on data |

## Definitions (Task 1)
- 1-D: window W = 32, step 1, output only for complete windows → 99,969 values. Even W → median =
  mean of the two middle values, stored as 2×median (integer), printed with one decimal (`.0`/`.5`).
- 2-D: k×k window, k odd (default 5) → single middle value. Borders: edge replication, output size = input size.
- Image format: binary PGM (P5, 8-bit), readable/writable without libraries in both languages.
- Timing: `load` (file → memory) is timed separately from `filter` (memory → result, incl. checksum).
  Writing the output file is never timed. Monotonic clock (`steady_clock` / `time.monotonic_ns`),
  CPU time (`CLOCK_PROCESS_CPUTIME_ID` / `time.process_time_ns`), peak RSS from GNU time `%M` (KiB).

## Run on the Pi
```sh
sudo apt install g++ time git
make                          # -O2 build + generate data
make visual                   # tests (must print 6 OK lines) + results/img/montage.png, zoom.png
sudo sh -c 'echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'
sh scripts/bench.sh both 1 1  # dry run
sh scripts/bench.sh both 10 3 # real run (several hours on a Pi 1 - start it in the evening)
python3 scripts/analyze.py results/raw_<timestamp>   # plots need matplotlib -> do this on the laptop
```
Run headless over SSH, nothing else running; `vcgencmd get_throttled` must be 0x0 before and after
(both are logged in environment.txt). Tip: run it inside `tmux` or with `nohup` so it survives SSH drops.

## Optional variations (good for the discussion)
- `python3 gen_data.py --kind sine`  → smooth signal with spikes: histogram method gets much faster
- `SIZE2=3 sh scripts/bench.sh 2d …` → 3×3 kernel; keeps more detail, less work per pixel
- `python3 gen_data.py --from photo.jpg` → your own photo (needs Pillow, only in this step)
