from dace import data, subsets, symbolic, types
from dace.codegen.codeobject import CodeObject
from dace.codegen.targets.target import TargetCodeGenerator
from dace.codegen.targets.cpu import cpp_array_expr, sym2cpp
from dace.graph import nodes

from dace.codegen import cppunparse


class ImmaterialCodeGen(TargetCodeGenerator):
    """ Code generator for data nodes with immaterial (i.e., generated
        from a function) storage. """

    target_name = 'Immaterial'
    language = 'cpp'

    def __init__(self, frame_codegen, sdfg):
        self._frame = frame_codegen
        self._dispatcher = frame_codegen.dispatcher
        dispatcher = self._dispatcher

        self.emitted_materialize_funcs = set()

        # Register dispatchers
        dispatcher.register_array_dispatcher(types.StorageType.Immaterial,
                                             self)

        cpu_storage = [
            types.StorageType.CPU_Heap, types.StorageType.CPU_Pinned,
            types.StorageType.CPU_Stack, types.StorageType.Register
        ]
        for storage_type in cpu_storage:
            dispatcher.register_copy_dispatcher(types.StorageType.Immaterial,
                                                storage_type, None, self)
            dispatcher.register_copy_dispatcher(
                storage_type, types.StorageType.Immaterial, None, self)

    def get_generated_codeobjects(self):
        return []  # Immaterial storage generates inline code

    @property
    def has_initializer(self):
        return False

    @property
    def has_finalizer(self):
        return False

    def allocate_array(self, sdfg, dfg, state_id, node, function_stream,
                       callsite_stream):
        callsite_stream.write("// allocate array\n", sdfg, state_id, node)

    def initialize_array(self, sdfg, dfg, state_id, node, function_stream,
                         callsite_stream):
        callsite_stream.write("// initialize_array " + node.data + "\n", sdfg,
                              state_id, node)

    def deallocate_array(self, sdfg, dfg, state_id, node, function_stream,
                         callsite_stream):
        callsite_stream.write("// deallocate_array", sdfg, state_id, node)

    def copy_memory(self, sdfg, dfg, state_id, src_node, dst_node, edge,
                    function_stream, callsite_stream):
        memlet = edge.data
        if (isinstance(src_node, nodes.AccessNode)
                and (src_node.desc(sdfg).materialize_func is not None)):
            function_stream.write(src_node.desc(sdfg).materialize_func)

            if edge.dst_conn is not None:
                arrayname = str(edge.dst_conn)
            else:
                arrayname = str(dst_node.desc)

            if isinstance(dst_node, nodes.Tasklet) or \
                    (dst_node.desc(sdfg).storage == types.StorageType.Register):
                callsite_stream.write(
                    self.memlet_definition(
                        sdfg, memlet, arrayname, direction="in"), sdfg,
                    state_id, [src_node, dst_node])
            else:
                callsite_stream.write("__dace_materialize(\"" + \
                                      sym2cpp(src_node) + "\", " + \
                                      sym2cpp(memlet.subset.min_element()[0]) +
                                      ", " + \
                                      sym2cpp(memlet.subset.min_element()[0] +
                                          memlet.subset.num_elements()) +
                                      ", " + sym2cpp(dst_node.data) + ");\n",
                                      sdfg, state_id, [src_node, dst_node])

        if (isinstance(dst_node, nodes.AccessNode)
                and (dst_node.desc(sdfg).materialize_func is not None)):
            # This case is pretty complicated due to how the rest of the
            # codegen works: This is not the place to actually copy code. In
            # the place where data is ready to be written there will be a call
            # __foo.write(foo) where foo is the local_name of the memlet that
            # "causes" the write. But this function is actually called when
            # we should set up everything for this call to work.
            # The above mentioned code is generated by process_out_memlets

            function_stream.write(dst_node.desc(sdfg).materialize_func)
            if isinstance(src_node, nodes.Tasklet) or \
                    (src_node.desc(sdfg).storage == types.StorageType.Register):
                callsite_stream.write(
                    self.memlet_definition(
                        sdfg, memlet, edge.src_conn, direction="out"), sdfg,
                    state_id, [src_node, dst_node])
            else:
                callsite_stream.write("__dace_serialize(\"" + \
                        sym2cpp(dst_node) + "\", " + \
                        sym2cpp(memlet.subset.min_element()[0]) +
                        ", " + \
                        sym2cpp(memlet.subset.min_element()[0] +
                            memlet.subset.num_elements()) +
                        ", " + sym2cpp(src_node.data) + ");\n",
                    sdfg, state_id, [src_node, dst_node])

    def memlet_definition(self, sdfg, memlet, local_name, direction="in"):
        if isinstance(memlet.data, data.Stream):
            return 'auto& %s = %s;\n' % (local_name, memlet.data)

        result = ('auto __%s = ' % local_name + self.memlet_view_ctor(
            sdfg, memlet, direction) + ';\n')

        # Allocate variable type
        memlet_type = '    dace::vec<%s, %s>' % (
            sdfg.arrays[memlet.data].dtype.ctype, sym2cpp(memlet.veclen))
        if memlet.subset.data_dims() == 0 and memlet.num_accesses >= 0:
            result += memlet_type + ' ' + local_name
            if direction == "in":
                result += ' = __%s;\n' % local_name
            else:
                result += ';\n'

        return result

    def memlet_view_ctor(self, sdfg, memlet, direction):
        useskip = False
        memlet_params = []

        memlet_name = memlet.data
        if isinstance(sdfg.arrays[memlet.data], data.Scalar):
            raise ValueError("This should never have happened")

        if isinstance(memlet.subset, subsets.Indices):
            # Compute address
            memlet_params.append(cpp_array_expr(sdfg, memlet, False))
            dims = 0

        elif isinstance(memlet.subset, subsets.Range):
            dims = len(memlet.subset.ranges)
            #memlet_params.append("")

            # Dimensions to remove from view (due to having one value)
            indexdims = []
            nonIndexDims = []

            for dim, (rb, re, rs) in enumerate(memlet.subset.ranges):
                if rs != 1:
                    useskip = True
                try:
                    if (re - rb) == 0:
                        indexdims.append(dim)
                    else:
                        nonIndexDims.append(dim)
                except TypeError:  # cannot determine truth value of Relational
                    nonIndexDims.append(dim)

            if len(nonIndexDims) > 1 and len(indexdims) > 0:
                raise NotImplementedError(
                    'subviews of more than one dimension ' + 'not implemented')
            elif len(
                    nonIndexDims) == 1 and len(indexdims) > 0:  # One dimension
                indexdim = nonIndexDims[0]

                # Contiguous dimension
                if indexdim == dims - 1:
                    memlet_params[-1] += ' + %s' % cpp_array_expr(
                        sdfg, memlet, False)
                    memlet_params.append(
                        '0, %s' % (sym2cpp(memlet.subset.ranges[-1][1] -
                                           memlet.subset.ranges[-1][0])))
                else:  # Non-contiguous dimension
                    useskip = True
                    memlet_params[-1] += ' + %s' % cpp_array_expr(
                        sdfg, memlet, False)
                    memlet_range = memlet.subset.ranges[indexdim]

                    # TODO(later): Access order
                    memlet_stride = functools.reduce(
                        lambda x, y: x * y,
                        sdfg.arrays[memlet.data].shape[indexdim + 1:])
                    memlet_stride = sym2cpp(memlet_stride)

                    memlet_params.append(
                        '0, %s, %s' %
                        (sym2cpp(memlet_range[1] - memlet_range[0]),
                         sym2cpp(memlet_stride)))

                # Subtract index dimensions from array dimensions
                dims -= len(indexdims)

            elif len(indexdims) == 0:
                for (rb, re, rs), s in zip(memlet.subset.ranges,
                                           sdfg.arrays[memlet.data].shape):
                    if useskip:
                        memlet_params.append(
                            '%s, %s, %s' %
                            (cppunparse.pyexpr2cpp(symbolic.symstr(rb)),
                             cppunparse.pyexpr2cpp(symbolic.symstr(s)),
                             cppunparse.pyexpr2cpp(symbolic.symstr(rs))))
                    else:
                        memlet_params.append(
                            '%s, %s' %
                            (cppunparse.pyexpr2cpp(symbolic.symstr(rb)),
                             cppunparse.pyexpr2cpp(symbolic.symstr(s))))
            elif len(nonIndexDims) == 0:  # Scalar view
                # Compute address
                memlet_params[-1] += ' + ' + cpp_array_expr(
                    sdfg, memlet, False)
                dims = 0

        else:
            raise RuntimeError(
                'Memlet type "%s" not implemented' % memlet.subset)

        if dims == 0:
            return 'dace::ArrayViewImmaterial%s%s<%s, %s, int32_t> ("%s", %s)' % (
                'In' if direction == "in" else "Out", 'Skip'
                if useskip else '', sdfg.arrays[memlet.data].dtype.ctype,
                symbolic.symstr(
                    memlet.veclen), memlet.data, ', '.join(memlet_params))
        else:
            return 'dace::ArrayViewImmaterial%s%s<%s, %s, int32_t, %s> ("%s", %s)' % (
                'In' if direction == "in" else "Out", 'Skip'
                if useskip else '', sdfg.arrays[memlet.data].dtype.ctype,
                symbolic.symstr(memlet.veclen), ', '.join([
                    str(s) for s in memlet.subset.bounding_box_size()
                ]), memlet.data, ', '.join(memlet_params))