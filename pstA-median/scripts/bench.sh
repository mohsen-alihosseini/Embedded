#!/bin/sh
# Benchmark driver for the Raspberry Pi. Run from the project root:
#   sh scripts/bench.sh <1d|2d|both> [trials] [reps] [methods]
#   trials : independent process launches per method and language (>= 10, default 10)
#   reps   : filter repetitions inside one process (default 3) -> first vs. later runs
#   methods: default "sort insertion bisect histogram"
# Language order alternates per trial (cpp,py / py,cpp) and the method order rotates,
# so drift and heating are spread over all combinations.
# End-to-end values come from GNU time (/usr/bin/time, NOT the shell builtin):
#   %e wall s, %U user s, %S sys s, %M peak resident set size KiB.
# Dry run first:  sh scripts/bench.sh both 1 1
set -e
TIME_BIN=${TIME_BIN:-/usr/bin/time}
[ -x "$TIME_BIN" ] || { echo "GNU time not found at $TIME_BIN (sudo apt install time)"; exit 1; }
MODE=${1:-both}
TRIALS=${2:-10}
REPS=${3:-3}
METHODS=${4:-"sort insertion bisect histogram"}
SIZE1=${SIZE1:-32}     # 1-D window
SIZE2=${SIZE2:-5}      # 2-D kernel k (k x k)
case $MODE in 1d) MODES=1d;; 2d) MODES=2d;; both) MODES="1d 2d";; *) echo "mode must be 1d, 2d or both"; exit 2;; esac

OUT=results/raw_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"
{
  echo "date: $(date -Is)"
  uname -a
  head -n 4 /etc/os-release
  g++ --version | head -n 1
  python3 --version
  echo "CXXFLAGS: $(cat build/CXXFLAGS 2>/dev/null)"
  echo "modes=$MODES trials=$TRIALS reps=$REPS methods=$METHODS size1d=$SIZE1 size2d=$SIZE2"
  echo "input sha256:"; sha256sum data/input.txt data/image_noisy.pgm
  echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
  echo "cur_freq_khz: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)"
  command -v vcgencmd >/dev/null && { vcgencmd measure_clock arm; vcgencmd measure_temp; vcgencmd get_throttled; }
  free -k
} > "$OUT/environment.txt" 2>&1

run_one() {   # lang mode method trial
  if [ "$2" = 1d ]; then IN=data/input.txt; SZ=$SIZE1; else IN=data/image_noisy.pgm; SZ=$SIZE2; fi
  if [ "$1" = cpp ]; then CMD="./build/median_filter $2 $3 $IN -"
  else                    CMD="python3 median_filter.py $2 $3 $IN -"; fi
  # (a) end-to-end, one filter run: process start -> exit
  "$TIME_BIN" -f "lang=$1 mode=$2 method=$3 trial=$4 wall_s=%e user_s=%U sys_s=%S maxrss_kib=%M" \
      -a -o "$OUT/e2e.txt" $CMD 1 $SZ 2>> "$OUT/inproc_single.txt"
  # (b) repeated computation inside one process
  $CMD "$REPS" $SZ 2>> "$OUT/inproc_reps.txt"
}

i=1
while [ $i -le "$TRIALS" ]; do
  for MD in $MODES; do
    ROT=$(echo $METHODS | awk -v s=$((i - 1)) '{for(k=0;k<NF;k++) printf "%s ", $(((k+s)%NF)+1)}')
    for M in $ROT; do
      if [ $((i % 2)) -eq 1 ]; then run_one cpp $MD $M $i; run_one py $MD $M $i
      else                          run_one py $MD $M $i;  run_one cpp $MD $M $i; fi
    done
  done
  echo "trial $i/$TRIALS done ($(date +%H:%M:%S))"
  i=$((i + 1))
done
command -v vcgencmd >/dev/null && { echo "after:"; vcgencmd measure_temp; vcgencmd get_throttled; } >> "$OUT/environment.txt"
echo "raw results in $OUT  ->  python3 scripts/analyze.py $OUT"
