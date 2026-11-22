// C++20 port of fxarb.bellman_ford (same semantics, same proofs: docs/theory.md).
// Built as an optional Python extension with pybind11; the pure-Python package never needs it.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <deque>
#include <optional>
#include <stdexcept>
#include <tuple>
#include <vector>

namespace py = pybind11;

namespace {

struct Result {
    std::optional<std::vector<int>> cycle;
    int rounds = 0;
    std::int64_t relaxations = 0;
    std::int64_t edge_scans = 0;
};

std::vector<int> cycle_from_pred(const std::vector<int>& pred, int start, int n) {
    int x = start;
    for (int i = 0; i < n; ++i) {
        x = pred[x];
        if (x < 0) throw std::runtime_error("predecessor walk reached the source");
    }
    std::vector<int> back{x};
    for (int y = pred[x]; y != x; y = pred[y]) back.push_back(y);
    back.push_back(x);
    return {back.rbegin(), back.rend()};
}

std::optional<std::vector<int>> find_pred_cycle(const std::vector<int>& pred) {
    const int n = static_cast<int>(pred.size());
    std::vector<int> state(n, 0);
    for (int s = 0; s < n; ++s) {
        if (state[s]) continue;
        int x = s;
        while (x >= 0 && !state[x]) { state[x] = s + 1; x = pred[x]; }
        if (x >= 0 && state[x] == s + 1) return cycle_from_pred(pred, x, n);
    }
    return std::nullopt;
}

class Graph {
  public:
    Graph(int n, const std::vector<std::tuple<int, int, double>>& edges) : n_(n) {
        if (n < 0) throw std::invalid_argument("n must be >= 0");
        u_.reserve(edges.size()); v_.reserve(edges.size()); w_.reserve(edges.size());
        for (const auto& [u, v, w] : edges) {
            if (u < 0 || u >= n || v < 0 || v >= n) throw std::out_of_range("edge endpoint out of range");
            u_.push_back(u); v_.push_back(v); w_.push_back(w);
        }
    }

    [[nodiscard]] Result bellman_ford(double eps, bool pred_check) const {
        Result r;
        std::vector<double> dist(n_, 0.0);
        std::vector<int> pred(n_, -1);
        const std::size_t m = u_.size();
        for (int rnd = 1; rnd <= n_; ++rnd) {
            int last = -1;
            for (std::size_t i = 0; i < m; ++i) {
                const double nd = dist[u_[i]] + w_[i];
                if (nd < dist[v_[i]] - eps) {
                    dist[v_[i]] = nd; pred[v_[i]] = u_[i]; last = v_[i]; ++r.relaxations;
                }
            }
            r.edge_scans += static_cast<std::int64_t>(m);
            r.rounds = rnd;
            if (last < 0) return r;
            if (rnd == n_) { r.cycle = cycle_from_pred(pred, last, n_); return r; }
            if (pred_check) {
                if (auto c = find_pred_cycle(pred)) { r.cycle = std::move(c); return r; }
            }
        }
        return r;
    }

    [[nodiscard]] Result spfa(double eps) const {
        Result r;
        if (n_ == 0) return r;
        // CSR adjacency
        std::vector<int> start(n_ + 1, 0);
        for (int u : u_) ++start[u + 1];
        for (int i = 0; i < n_; ++i) start[i + 1] += start[i];
        std::vector<int> to(u_.size());
        std::vector<double> wt(u_.size());
        std::vector<int> fill(start.begin(), start.end() - 1);
        for (std::size_t i = 0; i < u_.size(); ++i) { to[fill[u_[i]]] = v_[i]; wt[fill[u_[i]]++] = w_[i]; }

        std::vector<double> dist(n_, 0.0);
        std::vector<int> pred(n_, -1);
        std::deque<int> q;
        std::vector<char> in_q(n_, 1);
        for (int i = 0; i < n_; ++i) q.push_back(i);
        int passes = 1;
        std::int64_t remaining = n_, next_check = n_;
        while (!q.empty()) {
            const int u = q.front(); q.pop_front(); in_q[u] = 0;
            const double du = dist[u];
            for (int k = start[u]; k < start[u + 1]; ++k) {
                ++r.edge_scans;
                const int v = to[k];
                const double nd = du + wt[k];
                if (nd < dist[v] - eps) {
                    dist[v] = nd; pred[v] = u; ++r.relaxations;
                    if (passes >= n_) { r.cycle = cycle_from_pred(pred, v, n_); r.rounds = passes; return r; }
                    if (r.relaxations >= next_check) {
                        next_check += n_;
                        if (auto c = find_pred_cycle(pred)) { r.cycle = std::move(c); r.rounds = passes; return r; }
                    }
                    if (!in_q[v]) { in_q[v] = 1; q.push_back(v); }
                }
            }
            if (--remaining == 0 && !q.empty()) { ++passes; remaining = static_cast<std::int64_t>(q.size()); }
        }
        r.rounds = passes;
        return r;
    }

    [[nodiscard]] int n() const { return n_; }
    [[nodiscard]] std::size_t m() const { return u_.size(); }

  private:
    int n_;
    std::vector<int> u_, v_;
    std::vector<double> w_;
};

py::tuple to_py(const Result& r) {
    py::object cyc = r.cycle ? py::cast(*r.cycle) : py::none();
    return py::make_tuple(cyc, r.rounds, r.relaxations, r.edge_scans);
}

}  // namespace

PYBIND11_MODULE(fxarb_cpp, mod) {
    mod.doc() = "C++20 Bellman-Ford / SPFA negative-cycle search (optional accelerator for fxarb)";
    py::class_<Graph>(mod, "Graph")
        .def(py::init<int, const std::vector<std::tuple<int, int, double>>&>(), py::arg("n"), py::arg("edges"))
        .def("bellman_ford", [](const Graph& g, double eps, bool pred_check) {
                 py::gil_scoped_release nogil;
                 Result r = g.bellman_ford(eps, pred_check);
                 py::gil_scoped_acquire gil;
                 return to_py(r);
             }, py::arg("eps") = 1e-12, py::arg("pred_check") = false,
             "Returns (cycle or None, rounds, relaxations, edge_scans).")
        .def("spfa", [](const Graph& g, double eps) {
                 py::gil_scoped_release nogil;
                 Result r = g.spfa(eps);
                 py::gil_scoped_acquire gil;
                 return to_py(r);
             }, py::arg("eps") = 1e-12)
        .def_property_readonly("n", &Graph::n)
        .def_property_readonly("m", &Graph::m);
}
