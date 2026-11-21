#!/bin/sh
# Benchmark driver for the Raspberry Pi. Run from the project root:
#   sh scripts/bench.sh [trials] [reps] [methods]
#   trials : independent process launches per method and language (>= 10, default 10)
#   reps   : filter repetitions inside one process (default 3) -> first vs. later runs
#   methods: default "sort insertion bisect histogram"
# Language order alternates per trial (cpp,py / py,cpp) and the method order rotates,
# so drift and heating are spread over all combinations.
# End-to-end values come from GNU time (/usr/bin/time, NOT the shell builtin):
#   %e wall s, %U user s, %S sys s, %P CPU share (user+sys)/wall,
#   %M peak resident set size KiB, %w voluntary and %c involuntary context switches.
# Dry run first:  sh scripts/bench.sh 1 1
set -e
TIME_BIN=${TIME_BIN:-/usr/bin/time}
[ -x "$TIME_BIN" ] || { echo "GNU time not found at $TIME_BIN (sudo apt install time)"; exit 1; }
TRIALS=${1:-10}
REPS=${2:-3}
METHODS=${3:-"sort insertion bisect histogram"}
W=${W:-31}
IN=data/input.txt

OUT=results/raw_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"
{
  echo "date: $(date -Is)"
  echo "model: $( (tr -d '\0' < /proc/device-tree/model) 2>/dev/null)"
  echo "cpu: $(grep -m1 -E 'model name|Processor' /proc/cpuinfo | cut -d: -f2)"
  echo "cores (nproc): $(nproc)"
  echo "ram total: $(grep MemTotal /proc/meminfo | awk '{print $2" KiB"}')"
  uname -a
  head -n 4 /etc/os-release
  g++ --version | head -n 1
  python3 --version
  echo "CXXFLAGS: $(cat build/CXXFLAGS 2>/dev/null)"
  echo "trials=$TRIALS reps=$REPS methods=$METHODS W=$W"
  echo "input sha256: $(sha256sum $IN)"
  echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
  echo "cur_freq_khz: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)"
  command -v vcgencmd >/dev/null && { vcgencmd measure_clock arm; vcgencmd measure_temp; vcgencmd get_throttled; }
  echo "empty interpreter peak RSS: $("$TIME_BIN" -f '%M KiB' python3 -c pass 2>&1)"
  echo "sys.getsizeof(1000): $(python3 -c 'import sys; print(sys.getsizeof(1000))') bytes"
  free -k
} > "$OUT/environment.txt" 2>&1

run_one() {   # lang method trial
  if [ "$1" = cpp ]; then CMD="./build/median_filter $2 $IN -"
  else                    CMD="python3 median_filter.py $2 $IN -"; fi
  # (a) end-to-end, one filter run: process start -> exit
  "$TIME_BIN" -f "lang=$1 method=$2 trial=$3 wall_s=%e user_s=%U sys_s=%S cpu_pct=%P maxrss_kib=%M ctx_vol=%w ctx_invol=%c" \
      -a -o "$OUT/e2e.txt" $CMD 1 $W 2>> "$OUT/inproc_single.txt"
  # (b) repeated computation inside one process
  $CMD "$REPS" $W 2>> "$OUT/inproc_reps.txt"
}

i=1
while [ $i -le "$TRIALS" ]; do
  ROT=$(echo $METHODS | awk -v s=$((i - 1)) '{for(k=0;k<NF;k++) printf "%s ", $(((k+s)%NF)+1)}')
  for M in $ROT; do
    if [ $((i % 2)) -eq 1 ]; then run_one cpp $M $i; run_one py $M $i
    else                          run_one py $M $i;  run_one cpp $M $i; fi
  done
  echo "trial $i/$TRIALS done ($(date +%H:%M:%S))"
  i=$((i + 1))
done
command -v vcgencmd >/dev/null && { echo "after:"; vcgencmd measure_temp; vcgencmd get_throttled; } >> "$OUT/environment.txt"
echo "raw results in $OUT  ->  python3 scripts/analyze.py $OUT"
