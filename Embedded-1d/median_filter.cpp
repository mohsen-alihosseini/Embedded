// Sliding-window median filter benchmark - C++17, standard library only.
// Mirrors median_filter.py step for step.
//
// Input : ASCII file, one integer 0..4095 per line (12-bit ADC samples).
// Window: W samples, W odd (default 31), moved by one sample; one output per
//         complete window (N - W + 1 values).
// Median: the middle value of the sorted window (the 16th smallest for W = 31).
//         Because W is odd, the median is always one of the samples: an integer.
//
// Methods (same algorithm in both languages)
//   sort      copy the window, std::sort, take the middle
//   insertion sorted window with hand-written binary search + element-shifting loops
//   bisect    same sorted window with library calls: lower_bound+erase, upper_bound+insert
//   histogram running histogram (4096 bins) + moving median pointer (Huang, Yang & Tang 1979)
//
// Build : g++ -O2 -std=c++17 -o build/median_filter median_filter.cpp
// Usage : median_filter <method> <in.txt> <out.txt|-> [reps] [W]

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <sys/resource.h>

using Sample = std::int32_t;    // samples and medians 0..4095
using Sum    = std::int64_t;    // checksum <= 99,970 * 4,095 ~ 4.1e8 -> int64 is safe
constexpr int VMAX = 4096;      // value range 0..4095

static std::int64_t now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();          // monotonic
}
// Current RSS (KiB) or thread count of this process from /proc/self/status (Linux); -1 if unavailable
static long proc_status(const char* key) {
    std::ifstream f("/proc/self/status");
    std::string line, k = std::string(key) + ":";
    while (std::getline(f, line))
        if (line.compare(0, k.size(), k) == 0) return std::atol(line.c_str() + k.size());
    return -1;
}
static std::int64_t cpu_ns() {
    timespec ts; clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts);
    return std::int64_t(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}

// ---------------------------------------------------------------------
// hand-written sorted-array helpers (used by the insertion method)
// ---------------------------------------------------------------------
static inline std::size_t lower_bound_idx(const Sample* a, std::size_t n, Sample v) {
    std::size_t lo = 0, hi = n;
    while (lo < hi) { std::size_t mid = (lo + hi) / 2; if (a[mid] < v) lo = mid + 1; else hi = mid; }
    return lo;
}
static inline void insert_sorted(Sample* srt, std::size_t filled, Sample v) {
    std::size_t p = lower_bound_idx(srt, filled, v);
    for (std::size_t k = filled; k > p; --k) srt[k] = srt[k - 1];
    srt[p] = v;
}
static inline void replace_sorted(Sample* srt, std::size_t n, Sample old, Sample nw) {
    std::size_t k = lower_bound_idx(srt, n, old);
    for (; k + 1 < n; ++k) srt[k] = srt[k + 1];          // shift left over removed element
    std::size_t p = lower_bound_idx(srt, n - 1, nw);
    for (k = n - 1; k > p; --k) srt[k] = srt[k - 1];     // shift right to open a slot
    srt[p] = nw;
}

// ---------------------------------------------------------------------
// the four methods: fill out (one median per window) and return the checksum
// ---------------------------------------------------------------------
static Sum m_sort(const std::vector<Sample>& x, std::size_t W, std::vector<Sample>& out) {
    std::vector<Sample> buf(W); Sum cs = 0; const std::size_t mid = W / 2;
    for (std::size_t i = 0; i + W <= x.size(); ++i) {
        std::copy(x.begin() + i, x.begin() + i + W, buf.begin());   // copy window
        std::sort(buf.begin(), buf.end());                          // library sort
        Sample med = buf[mid]; out.push_back(med); cs += med;
    }
    return cs;
}
static Sum m_insertion(const std::vector<Sample>& x, std::size_t W, std::vector<Sample>& out) {
    std::vector<Sample> ring(W), srt(W);                 // ring buffer + sorted copy
    std::size_t filled = 0, head = 0; Sum cs = 0; const std::size_t mid = W / 2;
    for (Sample v : x) {
        if (filled < W) { ring[filled] = v; insert_sorted(srt.data(), filled, v); ++filled; }
        else {                                           // remove oldest, insert newest
            Sample old = ring[head]; ring[head] = v;
            head = (head + 1 == W) ? 0 : head + 1;
            replace_sorted(srt.data(), W, old, v);
        }
        if (filled == W) { Sample med = srt[mid]; out.push_back(med); cs += med; }
    }
    return cs;
}
static Sum m_bisect(const std::vector<Sample>& x, std::size_t W, std::vector<Sample>& out) {
    std::vector<Sample> srt; srt.reserve(W + 1); Sum cs = 0; const std::size_t mid = W / 2;
    for (std::size_t i = 0; i < x.size(); ++i) {
        if (i >= W) srt.erase(std::lower_bound(srt.begin(), srt.end(), x[i - W]));  // remove leaving sample
        srt.insert(std::upper_bound(srt.begin(), srt.end(), x[i]), x[i]);           // insert new sample
        if (i + 1 >= W) { Sample med = srt[mid]; out.push_back(med); cs += med; }
    }
    return cs;
}
static Sum m_histogram(const std::vector<Sample>& x, std::size_t W, std::vector<Sample>& out) {
    std::vector<std::int32_t> hist(VMAX, 0);
    const std::int64_t rank = std::int64_t(W / 2);      // 0-based rank of the median (15 for W = 31)
    std::int64_t m = 0, lt = 0; Sum cs = 0;              // m: median value, lt: samples < m
    for (std::size_t i = 0; i < x.size(); ++i) {
        Sample v = x[i];
        ++hist[v]; if (v < m) ++lt;
        if (i >= W) { Sample o = x[i - W]; --hist[o]; if (o < m) --lt; }
        if (i + 1 < W) continue;
        while (lt > rank)              { --m; lt -= hist[m]; }      // move pointer down
        while (lt + hist[m] <= rank)   { lt += hist[m]; ++m; }      // move pointer up
        out.push_back(Sample(m)); cs += m;                          // lt <= rank < lt + hist[m]
    }
    return cs;
}

// ---------------------------------------------------------------------
int main(int argc, char** argv) {
    const std::string methods[] = {"sort", "insertion", "bisect", "histogram"};
    Sum (*funcs[])(const std::vector<Sample>&, std::size_t, std::vector<Sample>&) =
        {m_sort, m_insertion, m_bisect, m_histogram};
    if (argc < 4) { std::cerr << "usage: median_filter <sort|insertion|bisect|histogram> <in> <out|-> [reps] [W]\n"; return 2; }
    const std::string method = argv[1], in = argv[2], outp = argv[3];
    int mi = -1; for (int i = 0; i < 4; ++i) if (method == methods[i]) mi = i;
    if (mi < 0) { std::cerr << "unknown method\n"; return 2; }
    const int reps = argc > 4 ? std::atoi(argv[4]) : 1;
    const long W = argc > 5 ? std::atol(argv[5]) : 31;
    if (W < 1 || W % 2 == 0) { std::cerr << "W must be odd and >= 1\n"; return 2; }

    const long rss_start = proc_status("VmRSS");         // program + C++ runtime, before any data

    // ---- load (timed separately) ----
    std::int64_t t0 = now_ns();
    std::vector<Sample> x;
    {
        std::ifstream f(in); if (!f) { std::cerr << "cannot open " << in << "\n"; return 1; }
        Sample v;
        while (f >> v) { if (v < 0 || v >= VMAX) { std::cerr << "value out of range 0..4095\n"; return 1; } x.push_back(v); }
    }
    std::int64_t load_ns = now_ns() - t0;
    const long rss_load = proc_status("VmRSS");          // + loaded input data

    // ---- filter only (no file output, no formatting) ----
    std::vector<Sample> out;
    for (int r = 0; r < reps; ++r) {
        out.clear(); out.reserve(x.size());
        std::int64_t c0 = cpu_ns(), w0 = now_ns();
        Sum cs = (x.size() >= std::size_t(W)) ? funcs[mi](x, std::size_t(W), out) : 0;
        std::int64_t w1 = now_ns(), c1 = cpu_ns();
        std::fprintf(stderr, "lang=cpp method=%s size=%ld rep=%d n_in=%zu load_ns=%lld filter_ns=%lld "
                     "filter_cpu_ns=%lld checksum=%lld n_out=%zu\n",
                     method.c_str(), W, r, x.size(), (long long)load_ns,
                     (long long)(w1 - w0), (long long)(c1 - c0), (long long)cs, out.size());
    }

    // ---- output (not part of the filter timing) ----
    if (outp != "-") {
        std::FILE* f = std::fopen(outp.c_str(), "w");
        for (Sample med : out) std::fprintf(f, "%d\n", med);
        std::fclose(f);
    }
    const long rss_end = proc_status("VmRSS"), threads = proc_status("Threads");
    rusage ru; getrusage(RUSAGE_SELF, &ru);                                                     // Linux: KiB
    std::fprintf(stderr, "lang=cpp method=%s maxrss_kib=%ld rss_start_kib=%ld rss_load_kib=%ld rss_end_kib=%ld threads=%ld\n",
                 method.c_str(), ru.ru_maxrss, rss_start, rss_load, rss_end, threads);
    return 0;
}
