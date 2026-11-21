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

bench: all
	sh scripts/bench.sh 10 3

clean:
	rm -rf build results/out tests/*.txt

.PHONY: all test bench clean
