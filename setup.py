from setuptools import setup, Extension
from Cython.Build import cythonize

setup(ext_modules=cythonize(
    Extension("src.cython_matching_engine", ["src/matching_engine.pyx"]),
    compiler_directives={"language_level": "3", "boundscheck": False}
))
