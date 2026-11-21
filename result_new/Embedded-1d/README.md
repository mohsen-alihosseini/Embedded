# PStA Embedded Linux – Topic 03 (median variant): C++ vs. Python for a sliding-window median filter

Research question: How do equivalent C++ and Python implementations of four sliding-window
median-filter algorithms differ in execution time and memory demand on a Raspberry Pi 1 B+,
and how does the choice of algorithm change the size of the difference between the languages?

## Files
| file | what it does |
|---|---|
| `gen_data.py` | writes `data/input.txt`: 100,000 integers 0..4095, seed 42 |
| `median_filter.py` | Python implementation of the four methods (standard library only) |
| `median_filter.cpp` | C++17 implementation of the same four methods |
| `tests/run_tests.sh` | hand-calculated cases (W = 3, 5, 31), brute-force reference, all 8 outputs identical |
| `scripts/bench.sh` | benchmark: end-to-end (GNU time) + filter-only + repeated runs, environment log |
| `scripts/analyze.py` | median / IQR / min / max, Python÷C++ ratios, boxplots |

## Command line
```
python3 median_filter.py <method> data/input.txt <out.txt|-> [reps] [W=31]
./build/median_filter    <method> data/input.txt <out.txt|-> [reps] [W=31]
method = sort | insertion | bisect | histogram
```

## The four methods (identical output)
| method | idea |
|---|---|
| `sort` | copy the window, library sort, take the middle value |
| `insertion` | keep the window sorted; remove the oldest and insert the newest value with hand-written binary search and shifting loops (+ ring buffer) |
| `bisect` | same as insertion, but with library calls (`bisect`/`insort` ↔ `lower_bound`/`erase`/`insert`) |
| `histogram` | 4096 counters + a pointer to the median value (Huang, Yang & Tang 1979) |

Window W = 31 (odd): the median is the single middle value of the sorted window, the 16th
smallest, so it is always one of the samples (an integer). Output: one value per complete window
(100,000 − 31 + 1 = 99,970 values). Other odd window sizes can be given as the last argument.

## Run on the Raspberry Pi
```sh
sudo apt install -y g++ make time tmux git
make                          # build with -O2, generate data/input.txt
make test                     # 4 OK lines, no FAIL
sudo sh -c 'echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'
tmux new -s bench
sh scripts/bench.sh 1 1       # quick test
sh scripts/bench.sh 10 3      # real run: 10 trials, 3 in-process repetitions (~45 min on a Pi 1 B+)
python3 scripts/analyze.py results/raw_<timestamp>
```
## What is measured (per program run, 10 trials per method and language)
| quantity | how | unit |
|---|---|---|
| end-to-end wall time | GNU time `%e` (start-up + load + filter + exit) | s |
| user / system CPU time | GNU time `%U` / `%S` | s |
| CPU usage of the whole run | GNU time `%P` = (user + system) / wall | % |
| context switches | GNU time `%w` (voluntary) / `%c` (involuntary) | count |
| load time | monotonic clock inside the program | ns |
| filter wall time / filter CPU time | monotonic clock / process CPU clock inside the program | ns |
| filter CPU usage | filter CPU time / filter wall time (analyze.py) | % |
| threads (cores used) | `/proc/self/status` Threads; board cores from `nproc` | count |
| RAM at start / after load / end | `/proc/self/status` VmRSS inside the program | KiB |
| peak RAM | GNU time `%M` | KiB |

`environment.txt` in each results folder records the board model, OS, compiler and Python
versions, CPU governor and clock, temperature, throttling, the empty interpreter's peak RSS and
`sys.getsizeof(1000)`.
