from setuptools import setup, find_packages
import glob
import os

# Find runtime and external library files by obtaining the module path and
# trimming the absolute path of the resulting files.
dace_path = os.path.dirname(os.path.abspath(__file__)) + '/dace/'
runtime_files = [
    f[len(dace_path):]
    for f in glob.glob(dace_path + 'runtime/include/**/*', recursive=True)
]
cub_files = [
    f[len(dace_path):]
    for f in glob.glob(dace_path + 'external/cub/cub/**/*', recursive=True)
] + [dace_path + 'external/cub/LICENSE.TXT']
hlslib_files = [
    f[len(dace_path):] for f in glob.glob(
        dace_path + 'external/hlslib/cmake/**/*', recursive=True)
] + [
    f[len(dace_path):] for f in glob.glob(
        dace_path + 'external/hlslib/include/**/*', recursive=True)
] + [dace_path + 'external/hlslib/LICENSE.md']

setup(
    name='dace',
    version='0.8.0',
    url='https://github.com/spcl/dace',
    author='SPCL @ ETH Zurich',
    author_email='talbn@inf.ethz.ch',
    description='Data-Centric Parallel Programming Framework',
    packages=find_packages(),
    package_data={
        '': [
            '*.yml', 'codegen/CMakeLists.txt', 'codegen/tools/*.cpp',
            '../diode/main.glade', '../diode/renderer.html',
            '../diode/renderer_util.js', '../diode/dagre.js',
            '../diode/Chart.bundle.min.js', '../diode/datahelper.js',
            '../diode/sdfg_renderer.js', '../diode/parallelization_button.js',
            '../diode/memory_button.js', '../diode/windowing.js',
            '../diode/global_vars.js', '../diode/subwindow.html',
            '../diode/DataViewSettings.js', '../diode/DataViewSettings.html',
            'external/moodycamel/*.h', 'external/moodycamel/LICENSE.md',
            'codegen/Xilinx_HLS.tcl.in'
        ] + runtime_files + cub_files + hlslib_files
    },
    include_package_data=True,
    install_requires=[
        'matplotlib', 'numpy', 'networkx >= 2.2', 'astunparse', 'sympy',
        'scipy', 'pyyaml', 'cmake', 'absl-py', 'ply', 'websockets', 'graphviz',
        'xdot @ git+https://github.com/tbennun/xdot.py.git'
    ],
    # install_requires for DIODE: pygobject
    scripts=['scripts/diode', 'scripts/dacelab'])