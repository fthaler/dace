#!/usr/bin/env python
import dace as dp

W = dp.symbol('W')
H = dp.symbol('H')


@dp.external_function
def mirror(i):
    return -i


@dp.external_function
def transpose(input, output):
    @dp.map(_[0:H, 0:W])
    def compute(i, j):
        a << input[j, i]
        b >> output[i, j]
        b = a


@dp.external_function
def bla(A, B, alpha):
    @dp.tasklet
    def something():
        a << A[0, 0]
        b >> B[0, 0]
        b = alpha * a


@dp.program
def myprogram(A, B, cst):
    dp.call(transpose, A, B)
    dp.call(bla, A, B, -dp.call(mirror, cst) + 1)
    bla(A, B, -dp.call(mirror, -cst) + 1)


if __name__ == '__main__':
    dp.compile(myprogram, dp.float32[W, H], dp.float32[H, W], dp.int32)