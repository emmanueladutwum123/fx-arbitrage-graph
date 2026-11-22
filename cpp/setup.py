from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

setup(
    ext_modules=[
        Pybind11Extension(
            "fxarb_cpp",
            ["src/fxarb_cpp.cpp"],
            cxx_std=20,
            extra_compile_args=["-O3", "-Wall", "-Wextra"],
        )
    ],
    cmdclass={"build_ext": build_ext},
)
