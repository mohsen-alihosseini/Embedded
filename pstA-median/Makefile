CXX      ?= g++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra

all: build/median_filter data/input.txt

build/median_filter: median_filter.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $<
	echo "$(CXX) $(CXXFLAGS)" > build/CXXFLAGS

data/input.txt: gen_data.py
	python3 gen_data.py

test: all
	sh tests/run_tests.sh

visual: test
	python3 scripts/compare_images.py results/img

bench: all
	sh scripts/bench.sh both 10 3

clean:
	rm -rf build results/img results/sig tests/*.txt tests/*.pgm

.PHONY: all test visual bench clean
