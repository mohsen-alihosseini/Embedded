#!/bin/sh
# Correctness checks, 4 methods x 2 languages, 1-D and 2-D.
#   1-D: hand-calculated sequences (W=4, W=3), brute-force reference, full dataset identical
#   2-D: hand-calculated 3x3 image, brute-force reference on a small image (k=3,5),
#        full test image identical for all 8 programs
# Also writes the full-size outputs to results/img/ and results/sig/ for compare_images.py.
set -e
cd "$(dirname "$0")/.."
M4="sort insertion bisect histogram"
mkdir -p results/img results/sig
run() {  # lang mode method in out size
  if [ "$1" = cpp ]; then ./build/median_filter "$2" "$3" "$4" "$5" 1 "$6" 2>/dev/null
  else python3 median_filter.py "$2" "$3" "$4" "$5" 1 "$6" 2>/dev/null; fi
}

# ---------- 1-D ----------
printf '5\n1\n9\n3\n7\n2\n8\n' > tests/hand.txt
# W=4: [5 1 9 3]->(3+5)/2=4.0 [1 9 3 7]->(3+7)/2=5.0 [9 3 7 2]->5.0 [3 7 2 8]->5.0
printf '4.0\n5.0\n5.0\n5.0\n' > tests/hand_w4.txt
# W=3: [5 1 9]->5 [1 9 3]->3 [9 3 7]->7 [3 7 2]->3 [7 2 8]->7
printf '5.0\n3.0\n7.0\n3.0\n7.0\n' > tests/hand_w3.txt
for W in 4 3; do for L in cpp py; do for M in $M4; do
  run $L 1d $M tests/hand.txt tests/o.txt $W
  cmp -s tests/o.txt tests/hand_w$W.txt || { echo "FAIL 1d hand W=$W $L $M"; exit 1; }
done; done; done
echo "1d hand-calculated (W=3, W=4): OK"

head -n 2000 data/input.txt > tests/small.txt
python3 - <<'EOF'
x=[int(l) for l in open("tests/small.txt")]; W=32
with open("tests/ref_small.txt","w") as f:
    for i in range(len(x)-W+1):
        w=sorted(x[i:i+W]); s=w[W//2-1]+w[W//2]
        f.write(f"{s//2}.{'5' if s%2 else '0'}\n")
EOF
for L in cpp py; do for M in $M4; do
  run $L 1d $M tests/small.txt tests/o.txt 32
  cmp -s tests/o.txt tests/ref_small.txt || { echo "FAIL 1d reference $L $M"; exit 1; }
done; done
echo "1d brute-force reference: OK"

for L in cpp py; do for M in $M4; do
  run $L 1d $M data/input.txt results/sig/out_${L}_${M}.txt 32
  cmp -s results/sig/out_${L}_${M}.txt results/sig/out_cpp_sort.txt || { echo "FAIL 1d full $L $M"; exit 1; }
done; done
echo "1d full dataset: all 8 outputs identical ($(wc -l < results/sig/out_cpp_sort.txt) values)"

# ---------- 2-D ----------
# Hand test, 3x3 image, k=3, edge replication:
#   10  20 30
#   40 250 60
#   70  80  0
# centre: all 9 values sorted 0 10 20 30 40 60 70 80 250 -> 40
# top-left: window rows [10 10 20] [10 10 20] [40 40 250] -> sorted 10 10 10 10 20 20 40 40 250 -> 20
python3 - <<'EOF'
open("tests/hand.pgm","wb").write(b"P5\n3 3\n255\n"+bytes([10,20,30,40,250,60,70,80,0]))
EOF
for L in cpp py; do for M in $M4; do
  run $L 2d $M tests/hand.pgm tests/o.pgm 3
  python3 -c "
d=open('tests/o.pgm','rb').read()[-9:]
assert d[4]==40 and d[0]==20, list(d)" || { echo "FAIL 2d hand $L $M"; exit 1; }
done; done
echo "2d hand-calculated 3x3 (centre=40, corner=20): OK"

# brute-force reference: 23x17 crop of the noisy image, k=3 and k=5
python3 - <<'EOF'
import sys; sys.path.insert(0,".")
from median_filter import read_pgm, write_pgm
w,h,px=read_pgm("data/image_noisy.pgm")
cw,ch,x0,y0=23,17,100,60
crop=[px[(y0+y)*w+x0+x] for y in range(ch) for x in range(cw)]
write_pgm("tests/crop.pgm",cw,ch,crop)
for k in (3,5):
    r=k//2; out=[]
    for y in range(ch):
        for x in range(cw):
            win=[crop[min(max(y+dy,0),ch-1)*cw+min(max(x+dx,0),cw-1)] for dy in range(-r,r+1) for dx in range(-r,r+1)]
            out.append(sorted(win)[len(win)//2])
    write_pgm(f"tests/ref_crop_k{k}.pgm",cw,ch,out)
EOF
for K in 3 5; do for L in cpp py; do for M in $M4; do
  run $L 2d $M tests/crop.pgm tests/o.pgm $K
  cmp -s tests/o.pgm tests/ref_crop_k$K.pgm || { echo "FAIL 2d reference k=$K $L $M"; exit 1; }
done; done; done
echo "2d brute-force reference (k=3, k=5): OK"

for L in cpp py; do for M in $M4; do
  run $L 2d $M data/image_noisy.pgm results/img/out_${L}_${M}.pgm 5
  cmp -s results/img/out_${L}_${M}.pgm results/img/out_cpp_sort.pgm || { echo "FAIL 2d full $L $M"; exit 1; }
done; done
echo "2d full image: all 8 outputs identical -> results/img/"
rm -f tests/o.txt tests/o.pgm
