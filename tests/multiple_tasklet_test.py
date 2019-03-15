#!/usr/bin/env python3
import numpy as np

import dace as dp
from dace.sdfg import SDFG
from dace.memlet import Memlet

# Constructs an SDFG with multiple tasklets manually and runs it
if __name__ == '__main__':
    print('SDFG multiple tasklet test')
    # Externals (parameters, symbols)
    N = dp.symbol('N')
    input = dp.ndarray([N], dp.int32)
    output = dp.ndarray([N], dp.int32)
    N.set(20)
    input[:] = dp.int32(5)
    output[:] = dp.int32(0)

    # Construct SDFG
    mysdfg = SDFG('multiple_tasklets')
    state = mysdfg.add_state()
    A = state.add_array('A', [N], dp.int32)
    B = state.add_array('B', [N], dp.int32)

    map_entry, map_exit = state.add_map('mymap', dict(i='0:N:2'))

    # Tasklet 1
    t1 = state.add_tasklet('task1', {'a'}, {'b'}, 'b = 5*a')
    state.add_edge(map_entry, None, t1, 'a', Memlet.simple(A, 'i'))
    state.add_edge(t1, 'b', map_exit, None, Memlet.simple(B, 'i'))

    # Tasklet 2
    t2 = state.add_tasklet('task2', {'a'}, {'b'}, 'b = a + a + a + a + a')
    state.add_edge(map_entry, None, t2, 'a', Memlet.simple(A, 'i+1'))
    state.add_edge(t2, 'b', map_exit, None, Memlet.simple(B, 'i+1'))

    state.add_edge(A, None, map_entry, None, Memlet.simple(A, '0:N'))
    state.add_edge(map_exit, None, B, None, Memlet.simple(B, '0:N'))

    # Left for debugging purposes
    mysdfg.draw_to_file()

    mysdfg(A=input, B=output, N=N)

    diff = np.linalg.norm(5 * input - output) / N.get()
    print("Difference:", diff)
    print("==== Program end ====")
    exit(0 if diff <= 1e-5 else 1)