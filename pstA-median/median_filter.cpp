// Median filter benchmark program - C++17, standard library only.
// Mirrors median_filter.py step for step.
//
// Modes
//   1d : sliding window over a 1-D integer signal (0..4095), window W (default 32),
//        one output per complete window (N - W + 1 values). Even W -> median = mean of the
//        two middle values; kept as s = 2*median and printed as s/2 + ".0" / ".5".
//   2d : k x k window (k odd, default 5) over an 8-bit grayscale PGM image (P5).
//        Borders: edge replication (clamp), output has the same size as the input.
//
// Methods (same algorithm in both languages)
//   sort      copy the window, std::sort, take the middle
//   insertion sorted window with hand-written binary search + element-shifting loops
//   bisect    same sorted window with library calls: lower_bound+erase, upper_bound+insert
//   histogram running histogram + moving median pointer (Huang, Yang & Tang 1979)
//
// Build : g++ -O2 -std=c++17 -o build/median_filter median_filter.cpp
// Usage : median_filter 1d <method> <in.txt> <out.txt|-> [reps] [W]
//         median_filter 2d <method> <in.pgm> <out.pgm|-> [reps] [k]

#include <algorithm>
#include <cctype>
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

using Sample = std::int32_t;    // 1-D samples 0..4095; also used for 2-D pixels after loading
using Sum    = std::int64_t;    // checksums: 1-D < 8.2e8, 2-D < 255 * pixels -> int64 is safe

static std::int64_t now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();          // monotonic
}
static std::int64_t cpu_ns() {
    timespec ts; clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts);
    return std::int64_t(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}

// =====================================================================
// shared helpers (hand-written sorted-array operations)
// =====================================================================
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
    for (; k + 1 < n; ++k) srt[k] = srt[k + 1];
    std::size_t p = lower_bound_idx(srt, n - 1, nw);
    for (k = n - 1; k > p; --k) srt[k] = srt[k - 1];
    srt[p] = nw;
}
static inline Sum two_median(const Sample* srt, std::size_t W) {
    return (W % 2 == 0) ? Sum(srt[W / 2 - 1]) + srt[W / 2] : 2 * Sum(srt[W / 2]);
}

// =====================================================================
// 1-D methods: fill out (2*median per window) and return checksum
// =====================================================================
static Sum s1_sort(const std::vector<Sample>& x, std::size_t W, std::vector<Sum>& out) {
    std::vector<Sample> buf(W); Sum cs = 0;
    for (std::size_t i = 0; i + W <= x.size(); ++i) {
        std::copy(x.begin() + i, x.begin() + i + W, buf.begin());
        std::sort(buf.begin(), buf.end());
        Sum s = two_median(buf.data(), W); out.push_back(s); cs += s;
    }
    return cs;
}
static Sum s1_insertion(const std::vector<Sample>& x, std::size_t W, std::vector<Sum>& out) {
    std::vector<Sample> ring(W), srt(W);
    std::size_t filled = 0, head = 0; Sum cs = 0;
    for (Sample v : x) {
        if (filled < W) { ring[filled] = v; insert_sorted(srt.data(), filled, v); ++filled; }
        else {
            Sample old = ring[head]; ring[head] = v;
            head = (head + 1 == W) ? 0 : head + 1;
            replace_sorted(srt.data(), W, old, v);
        }
        if (filled == W) { Sum s = two_median(srt.data(), W); out.push_back(s); cs += s; }
    }
    return cs;
}
static Sum s1_bisect(const std::vector<Sample>& x, std::size_t W, std::vector<Sum>& out) {
    std::vector<Sample> srt; srt.reserve(W + 1); Sum cs = 0;
    for (std::size_t i = 0; i < x.size(); ++i) {
        if (i >= W) srt.erase(std::lower_bound(srt.begin(), srt.end(), x[i - W]));
        srt.insert(std::upper_bound(srt.begin(), srt.end(), x[i]), x[i]);      // = insort
        if (i + 1 >= W) { Sum s = two_median(srt.data(), W); out.push_back(s); cs += s; }
    }
    return cs;
}
static Sum s1_histogram(const std::vector<Sample>& x, std::size_t W, std::vector<Sum>& out) {
    std::vector<std::int32_t> hist(4096, 0);
    const bool even = W % 2 == 0;
    const std::int64_t rank = even ? std::int64_t(W / 2) - 1 : std::int64_t(W / 2);
    std::int64_t m = 0, lt = 0; Sum cs = 0;
    for (std::size_t i = 0; i < x.size(); ++i) {
        Sample v = x[i];
        ++hist[v]; if (v < m) ++lt;
        if (i >= W) { Sample o = x[i - W]; --hist[o]; if (o < m) --lt; }
        if (i + 1 < W) continue;
        while (lt > rank)              { --m; lt -= hist[m]; }
        while (lt + hist[m] <= rank)   { lt += hist[m]; ++m; }
        std::int64_t hi = m;
        if (even && lt + hist[m] <= rank + 1) { hi = m + 1; while (hist[hi] == 0) ++hi; }
        Sum s = even ? m + hi : 2 * m;
        out.push_back(s); cs += s;
    }
    return cs;
}

// =====================================================================
// 2-D methods: img is row-major, out gets w*h pixels
// =====================================================================
static std::vector<Sample> pad_clamp(const std::vector<Sample>& img, int w, int h, int r, int& pw) {
    pw = w + 2 * r;
    std::vector<Sample> P; P.reserve(std::size_t(pw) * (h + 2 * r));
    for (int yy = -r; yy < h + r; ++yy) {
        int y = yy < 0 ? 0 : yy >= h ? h - 1 : yy;
        const Sample* row = &img[std::size_t(y) * w];
        for (int i = 0; i < r; ++i) P.push_back(row[0]);
        P.insert(P.end(), row, row + w);
        for (int i = 0; i < r; ++i) P.push_back(row[w - 1]);
    }
    return P;
}
static void s2_sort(const std::vector<Sample>& img, int w, int h, int k, std::vector<Sample>& out) {
    int pw; auto P = pad_clamp(img, w, h, k / 2, pw);
    const int mid = (k * k) / 2;
    std::vector<Sample> buf(std::size_t(k) * k);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            std::size_t base = std::size_t(y) * pw + x, n = 0;
            for (int dy = 0; dy < k; ++dy) {
                std::size_t s = base + std::size_t(dy) * pw;
                std::copy(P.begin() + s, P.begin() + s + k, buf.begin() + n); n += k;
            }
            std::sort(buf.begin(), buf.end());
            out[std::size_t(y) * w + x] = buf[mid];
        }
}
static void s2_insertion(const std::vector<Sample>& img, int w, int h, int k, std::vector<Sample>& out) {
    int pw; auto P = pad_clamp(img, w, h, k / 2, pw);
    const std::size_t n = std::size_t(k) * k, mid = n / 2;
    std::vector<Sample> srt(n);
    for (int y = 0; y < h; ++y) {
        std::size_t filled = 0;
        for (int dy = 0; dy < k; ++dy) {
            std::size_t base = std::size_t(y + dy) * pw;
            for (int dx = 0; dx < k; ++dx) { insert_sorted(srt.data(), filled, P[base + dx]); ++filled; }
        }
        out[std::size_t(y) * w] = srt[mid];
        for (int x = 1; x < w; ++x) {
            for (int dy = 0; dy < k; ++dy) {
                std::size_t base = std::size_t(y + dy) * pw;
                replace_sorted(srt.data(), n, P[base + x - 1], P[base + x + k - 1]);
            }
            out[std::size_t(y) * w + x] = srt[mid];
        }
    }
}
static void s2_bisect(const std::vector<Sample>& img, int w, int h, int k, std::vector<Sample>& out) {
    int pw; auto P = pad_clamp(img, w, h, k / 2, pw);
    const std::size_t mid = (std::size_t(k) * k) / 2;
    std::vector<Sample> srt; srt.reserve(std::size_t(k) * k + 1);
    for (int y = 0; y < h; ++y) {
        srt.clear();
        for (int dy = 0; dy < k; ++dy) {
            std::size_t base = std::size_t(y + dy) * pw;
            for (int dx = 0; dx < k; ++dx) {
                Sample v = P[base + dx];
                srt.insert(std::upper_bound(srt.begin(), srt.end(), v), v);
            }
        }
        out[std::size_t(y) * w] = srt[mid];
        for (int x = 1; x < w; ++x) {
            for (int dy = 0; dy < k; ++dy) {
                std::size_t base = std::size_t(y + dy) * pw;
                srt.erase(std::lower_bound(srt.begin(), srt.end(), P[base + x - 1]));
                Sample v = P[base + x + k - 1];
                srt.insert(std::upper_bound(srt.begin(), srt.end(), v), v);
            }
            out[std::size_t(y) * w + x] = srt[mid];
        }
    }
}
static void s2_histogram(const std::vector<Sample>& img, int w, int h, int k, std::vector<Sample>& out) {
    int pw; auto P = pad_clamp(img, w, h, k / 2, pw);
    const int rank = (k * k) / 2;
    std::vector<std::int32_t> hist(256);
    for (int y = 0; y < h; ++y) {
        std::fill(hist.begin(), hist.end(), 0);
        for (int dy = 0; dy < k; ++dy) {
            std::size_t base = std::size_t(y + dy) * pw;
            for (int dx = 0; dx < k; ++dx) ++hist[P[base + dx]];
        }
        int m = 0, lt = 0;
        while (lt + hist[m] <= rank) { lt += hist[m]; ++m; }
        out[std::size_t(y) * w] = m;
        for (int x = 1; x < w; ++x) {
            for (int dy = 0; dy < k; ++dy) {
                std::size_t base = std::size_t(y + dy) * pw;
                Sample o = P[base + x - 1];     --hist[o]; if (o < m) --lt;
                Sample v = P[base + x + k - 1]; ++hist[v]; if (v < m) ++lt;
            }
            while (lt > rank)            { --m; lt -= hist[m]; }
            while (lt + hist[m] <= rank) { lt += hist[m]; ++m; }
            out[std::size_t(y) * w + x] = m;
        }
    }
}

// =====================================================================
// PGM (P5, maxval 255) I/O
// =====================================================================
static bool read_pgm(const std::string& path, int& w, int& h, std::vector<Sample>& px) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    std::string tok[4];
    for (int i = 0; i < 4; ++i) {
        int c = f.get();
        while (true) {
            while (c != EOF && std::isspace(c)) c = f.get();
            if (c == '#') { while (c != EOF && c != '\n') c = f.get(); continue; }
            break;
        }
        while (c != EOF && !std::isspace(c)) { tok[i] += char(c); c = f.get(); }
        // the whitespace after maxval has been consumed by the last get()
    }
    if (tok[0] != "P5" || tok[3] != "255") return false;
    w = std::stoi(tok[1]); h = std::stoi(tok[2]);
    std::vector<unsigned char> raw(std::size_t(w) * h);
    f.read(reinterpret_cast<char*>(raw.data()), raw.size());
    if (std::size_t(f.gcount()) != raw.size()) return false;
    px.assign(raw.begin(), raw.end());
    return true;
}
static void write_pgm(const std::string& path, int w, int h, const std::vector<Sample>& px) {
    std::FILE* f = std::fopen(path.c_str(), "wb");
    std::fprintf(f, "P5\n%d %d\n255\n", w, h);
    std::vector<unsigned char> raw(px.begin(), px.end());
    std::fwrite(raw.data(), 1, raw.size(), f);
    std::fclose(f);
}

// =====================================================================
int main(int argc, char** argv) {
    const std::string methods[] = {"sort", "insertion", "bisect", "histogram"};
    if (argc < 5) { std::cerr << "usage: median_filter <1d|2d> <sort|insertion|bisect|histogram> <in> <out|-> [reps] [size]\n"; return 2; }
    const std::string mode = argv[1], method = argv[2], in = argv[3], outp = argv[4];
    int mi = -1; for (int i = 0; i < 4; ++i) if (method == methods[i]) mi = i;
    if ((mode != "1d" && mode != "2d") || mi < 0) { std::cerr << "bad mode or method\n"; return 2; }
    const int reps = argc > 5 ? std::atoi(argv[5]) : 1;
    const int size = argc > 6 ? std::atoi(argv[6]) : (mode == "1d" ? 32 : 5);
    if (size < 1 || (mode == "2d" && size % 2 == 0)) { std::cerr << "bad size (2d needs odd k)\n"; return 2; }

    // ---- load (timed separately) ----
    std::int64_t t0 = now_ns();
    std::vector<Sample> x; int w = 0, h = 0;
    if (mode == "1d") {
        std::ifstream f(in); if (!f) { std::cerr << "cannot open " << in << "\n"; return 1; }
        Sample v;
        while (f >> v) { if (v < 0 || v > 4095) { std::cerr << "value out of range 0..4095\n"; return 1; } x.push_back(v); }
    } else if (!read_pgm(in, w, h, x)) { std::cerr << "cannot read P5/255 PGM " << in << "\n"; return 1; }
    std::int64_t load_ns = now_ns() - t0;
    const std::size_t n_in = x.size();

    // ---- filter only (no file output, no formatting) ----
    std::vector<Sum> out1; std::vector<Sample> out2;
    for (int r = 0; r < reps; ++r) {
        std::int64_t c0 = cpu_ns(), w0 = now_ns();
        Sum cs = 0; std::size_t n_out;
        if (mode == "1d") {
            out1.clear(); out1.reserve(x.size());
            if (x.size() >= std::size_t(size)) {
                Sum (*f[])(const std::vector<Sample>&, std::size_t, std::vector<Sum>&) =
                    {s1_sort, s1_insertion, s1_bisect, s1_histogram};
                cs = f[mi](x, size, out1);
            }
            n_out = out1.size();
        } else {
            out2.assign(std::size_t(w) * h, 0);
            void (*f[])(const std::vector<Sample>&, int, int, int, std::vector<Sample>&) =
                {s2_sort, s2_insertion, s2_bisect, s2_histogram};
            f[mi](x, w, h, size, out2);
            for (Sample p : out2) cs += p;              // checksum (same in Python)
            n_out = out2.size();
        }
        std::int64_t w1 = now_ns(), c1 = cpu_ns();
        std::fprintf(stderr, "lang=cpp mode=%s method=%s size=%d rep=%d n_in=%zu load_ns=%lld filter_ns=%lld "
                     "filter_cpu_ns=%lld checksum=%lld n_out=%zu\n",
                     mode.c_str(), method.c_str(), size, r, n_in, (long long)load_ns,
                     (long long)(w1 - w0), (long long)(c1 - c0), (long long)cs, n_out);
    }

    // ---- output (not part of the filter timing) ----
    if (outp != "-") {
        if (mode == "1d") {
            std::FILE* f = std::fopen(outp.c_str(), "w");
            for (Sum s : out1) std::fprintf(f, "%lld.%c\n", (long long)(s / 2), (s % 2) ? '5' : '0');
            std::fclose(f);
        } else write_pgm(outp, w, h, out2);
    }
    rusage ru; getrusage(RUSAGE_SELF, &ru);
    std::fprintf(stderr, "lang=cpp mode=%s method=%s maxrss_kib=%ld\n", mode.c_str(), method.c_str(), ru.ru_maxrss);
    return 0;
}
