#ifndef __DACE_RUNTIME_H
#define __DACE_RUNTIME_H

// Necessary headers
#include <cstdio>
#include <cmath>
#include <numeric>
#include <tuple>
#include <cstring>

// The order in which these are included matters - sorting them
// alphabetically causes compilation to fail.
#include "types.h"
#include "vector.h"
#include "intset.h"
#include "math.h"
#include "complex.h"
#include "pyinterop.h"
#include "copy.h"
#include "view.h"
#include "stream.h"
#include "os.h"

#ifdef __CUDACC__
#include "cuda/copy.cuh"
#include "cuda/dynmap.cuh"
#else
#include "cudainterop.h"
#endif

#ifdef DACE_XILINX
#include "xilinx/host.h"
#endif


#endif  // __DACE_RUNTIME_H