# fxarb-cpp (optional)

A C++20 port of `fxarb.bellman_ford` and `fxarb.spfa`, exposed to Python with pybind11.
The pure-Python package never needs it; `scripts/benchmark.py` adds C++ columns when it is
installed, and `tests/test_cpp.py` checks it returns exactly the same cycles, round counts and
edge-scan counts as the Python code.

```bash
pip install ./cpp          # needs a C++20 compiler
python -c "import fxarb_cpp; print(fxarb_cpp.Graph(2, [(0, 1, -0.1), (1, 0, 0.05)]).bellman_ford())"
```

On macOS, if the build fails with `'cstddef' file not found`, the Command Line Tools'
libc++ headers are missing; build with Homebrew LLVM instead:
`CC=$(brew --prefix llvm)/bin/clang CXX=$(brew --prefix llvm)/bin/clang++ pip install ./cpp`.
