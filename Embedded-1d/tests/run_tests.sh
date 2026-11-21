#!/bin/sh
# Correctness checks for all 4 methods x 2 languages:
#   (1) hand-calculated sequences (W=3, W=5 and the specified W=31)
#   (2) brute-force reference on the first 2000 samples (W=31)
#   (3) full dataset: all 8 outputs byte-identical
set -e
cd "$(dirname "$0")/.."
M4="sort insertion bisect histogram"
mkdir -p results/out
run() {  # lang method in out W
  if [ "$1" = cpp ]; then ./build/median_filter "$2" "$3" "$4" 1 "$5" 2>/dev/null
  else python3 median_filter.py "$2" "$3" "$4" 1 "$5" 2>/dev/null; fi
}

# (1a) input 5 1 9 3 7 2 8
printf '5\n1\n9\n3\n7\n2\n8\n' > tests/hand.txt
# W=3: [5 1 9]->sorted 1 5 9->5   [1 9 3]->1 3 9->3   [9 3 7]->3 7 9->7   [3 7 2]->2 3 7->3   [7 2 8]->2 7 8->7
printf '5\n3\n7\n3\n7\n' > tests/hand_w3.txt
# W=5: [5 1 9 3 7]->1 3 5 7 9->5   [1 9 3 7 2]->1 2 3 7 9->3   [9 3 7 2 8]->2 3 7 8 9->7
printf '5\n3\n7\n' > tests/hand_w5.txt
for W in 3 5; do for L in cpp py; do for M in $M4; do
  run $L $M tests/hand.txt tests/o.txt $W
  cmp -s tests/o.txt tests/hand_w$W.txt || { echo "FAIL hand W=$W $L $M"; exit 1; }
done; done; done
echo "hand-calculated (W=3, W=5): OK"

# (1b) the specified window W=31
# ramp 1..40: window i holds i+1 ... i+31 -> the 16th smallest (middle) is i+16
#   -> outputs 16, 17, ..., 25  (40 - 31 + 1 = 10 outputs)
seq 1 40 > tests/hand31_ramp.txt
seq 16 25 > tests/hand31_ramp_exp.txt
# 40 x 100 with one spike 4000: every window has >= 30 values of 100 -> median 100 (spike removed)
python3 -c "print('\n'.join('4000' if i == 10 else '100' for i in range(40)))" > tests/hand31_spike.txt
for i in 1 2 3 4 5 6 7 8 9 10; do echo "100"; done > tests/hand31_spike_exp.txt
for T in ramp spike; do for L in cpp py; do for M in $M4; do
  run $L $M tests/hand31_$T.txt tests/o.txt 31
  cmp -s tests/o.txt tests/hand31_${T}_exp.txt || { echo "FAIL hand W=31 $T $L $M"; exit 1; }
done; done; done
echo "hand-calculated with W=31 (ramp 1..40 -> 16..25, spike -> 100): OK"

# (2) brute-force reference: sort every window separately
head -n 2000 data/input.txt > tests/small.txt
python3 - <<'EOF'
x = [int(l) for l in open("tests/small.txt")]; W = 31
with open("tests/ref_small.txt", "w") as f:
    for i in range(len(x) - W + 1):
        f.write(f"{sorted(x[i:i + W])[W // 2]}\n")
EOF
for L in cpp py; do for M in $M4; do
  run $L $M tests/small.txt tests/o.txt 31
  cmp -s tests/o.txt tests/ref_small.txt || { echo "FAIL reference $L $M"; exit 1; }
done; done
echo "brute-force reference (first 2000 samples): OK"

# (3) full dataset
for L in cpp py; do for M in $M4; do
  run $L $M data/input.txt results/out/out_${L}_${M}.txt 31
  cmp -s results/out/out_${L}_${M}.txt results/out/out_cpp_sort.txt || { echo "FAIL full $L $M"; exit 1; }
done; done
echo "full dataset: all 8 outputs identical ($(wc -l < results/out/out_cpp_sort.txt) values): OK"
rm -f tests/o.txt
