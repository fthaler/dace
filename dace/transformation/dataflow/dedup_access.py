# Copyright 2019-2020 ETH Zurich and the DaCe authors. All rights reserved.
""" Contains the access deduplication transformation. """

from collections import defaultdict
import copy
import itertools
from typing import List, Set

from dace import data, dtypes, sdfg as sd, subsets, symbolic, registry
from dace.memlet import Memlet
from dace.sdfg import nodes
from dace.sdfg import utils as sdutil
from dace.transformation import pattern_matching


@registry.autoregister_params(singlestate=True)
class DeduplicateAccess(pattern_matching.Transformation):
    """ 
    This transformation takes a node that is connected to multiple destinations
    with overlapping memlets, and consolidates those accesses through a 
    transient array or scalar.
    """

    _map_entry = nodes.MapEntry(nodes.Map('_', [], []))
    _node1 = nodes.Node()
    _node2 = nodes.Node()

    @staticmethod
    def expressions():
        state = sd.SDFGState()
        state.add_nedge(DeduplicateAccess._map_entry, DeduplicateAccess._node1,
                        Memlet())
        state.add_nedge(DeduplicateAccess._map_entry, DeduplicateAccess._node2,
                        Memlet())
        return [state]

    @staticmethod
    def can_be_applied(graph: sd.SDFGState,
                       candidate,
                       expr_index,
                       sdfg,
                       strict=False):
        map_entry = graph.node(candidate[DeduplicateAccess._map_entry])
        nid1 = candidate[DeduplicateAccess._node1]
        node1 = graph.node(nid1)
        nid2 = candidate[DeduplicateAccess._node2]
        node2 = graph.node(nid2)

        # Two nodes must be ordered (avoid duplicates/nondeterminism)
        if nid1 >= nid2:
            return False

        # Two nodes must belong to same connector
        edges1 = set(e.src_conn for e in graph.edges_between(map_entry, node1))
        edges2 = set(e.src_conn for e in graph.edges_between(map_entry, node2))
        if len(edges1 & edges2) == 0:
            return False

        # For each common connector
        for conn in (edges1 & edges2):
            # Deduplication: Only apply to first pair of edges
            node_ids = [
                graph.node_id(e.dst) for e in graph.out_edges(map_entry)
                if e.src_conn == conn
            ]
            if any(nid < nid1 for nid in node_ids):
                return False
            if any(nid < nid2 for nid in node_ids if nid != nid1):
                return False

            # Matching condition: Bounding box union of subsets is smaller than
            # adding the subset sizes
            memlets: List[Memlet] = [
                e.data for e in graph.out_edges(map_entry) if e.src_conn == conn
            ]
            union_subset = memlets[0].subset
            for memlet in memlets[1:]:
                union_subset = subsets.bounding_box_union(
                    union_subset, memlet.subset)
            if union_subset.num_elements() < sum(m.subset.num_elements()
                                                 for m in memlets):
                return True

        return False

    @staticmethod
    def match_to_str(graph, candidate):
        return str(graph.node(candidate[DeduplicateAccess._map_entry]))

    @staticmethod
    def are_subsets_contiguous(subset_a: subsets.Subset,
                               subset_b: subsets.Subset,
                               dim: int = None) -> bool:
        if dim is not None:
            # A version that only checks for contiguity in certain
            # dimension (e.g., to prioritize stride-1 range)
            if (not isinstance(subset_a, subsets.Range)
                    or not isinstance(subset_b, subsets.Range)):
                raise NotImplementedError('Contiguous subset check only '
                                          'implemented for ranges')

            # Other dimensions must be equal
            for i, (s1, s2) in enumerate(zip(subset_a.ranges, subset_b.ranges)):
                if i == dim:
                    continue
                if s1[0] != s2[0] or s1[1] != s2[1] or s1[2] != s2[2]:
                    return False

            # Set of conditions for contiguous dimension
            ab = (subset_a[dim][1] + 1) == subset_b[dim][0]
            a_overlap_b = subset_a[dim][1] >= subset_b[dim][0]
            ba = (subset_b[dim][1] + 1) == subset_a[dim][0]
            b_overlap_a = subset_b[dim][1] >= subset_a[dim][0]
            # NOTE: Must check with "==" due to sympy using special types
            return (ab == True or a_overlap_b == True or ba == True
                    or b_overlap_a == True)

        # General case
        bbunion = subsets.bounding_box_union(subset_a, subset_b)
        return bbunion.num_elements() == (subset_a.num_elements() +
                                          subset_b.num_elements())

    @staticmethod
    def find_contiguous_subsets(subset_list: List[subsets.Subset],
                                dim: int = None) -> Set[subsets.Subset]:
        """ 
        Finds the set of largest contiguous subsets in a list of subsets. 
        :param subsets: Iterable of subset objects.
        :param dim: Check for contiguity only for the specified dimension.
        :return: A list of contiguous subsets.
        """
        # Currently O(n^3) worst case. TODO: improve
        subset_set = set(
            subsets.Range.from_indices(s) if isinstance(s, subsets.Indices
                                                        ) else s
            for s in subset_list)
        while True:
            for sa, sb in itertools.product(subset_set, subset_set):
                if sa is sb:
                    continue
                if sa.covers(sb):
                    subset_set.remove(sb)
                    break
                elif sb.covers(sa):
                    subset_set.remove(sa)
                    break
                elif DeduplicateAccess.are_subsets_contiguous(sa, sb, dim):
                    subset_set.remove(sa)
                    subset_set.remove(sb)
                    subset_set.add(subsets.bounding_box_union(sa, sb))
                    break
            else:  # No modification performed
                break
        return subset_set

    def apply(self, sdfg: sd.SDFG):
        graph: sd.SDFGState = sdfg.nodes()[self.state_id]
        map_entry = graph.node(self.subgraph[DeduplicateAccess._map_entry])
        node1 = graph.node(self.subgraph[DeduplicateAccess._node1])
        node2 = graph.node(self.subgraph[DeduplicateAccess._node2])

        # Steps:
        # 1. Find unique subsets
        # 2. Find sets of contiguous subsets
        # 3. Create transients for subsets
        # 4. Redirect edges through new transients

        edges1 = set(e.src_conn for e in graph.edges_between(map_entry, node1))
        edges2 = set(e.src_conn for e in graph.edges_between(map_entry, node2))

        # Only apply to first connector (determinism)
        conn = sorted(edges1 & edges2)[0]

        edges = [e for e in graph.out_edges(map_entry) if e.src_conn == conn]

        # Get original data descriptor
        dname = edges[0].data.data
        desc = sdfg.arrays[edges[0].data.data]

        # Get unique subsets
        unique_subsets = set(e.data.subset for e in edges)

        # Find largest contiguous subsets
        try:
            # Start from stride-1 dimension
            contiguous_subsets = self.find_contiguous_subsets(
                unique_subsets,
                dim=next(i for i, s in enumerate(desc.strides) if s == 1))
        except (StopIteration, NotImplementedError):
            contiguous_subsets = unique_subsets

        # Then find subsets for rest of the dimensions
        contiguous_subsets = self.find_contiguous_subsets(contiguous_subsets)

        # Map original edges to subsets
        edge_mapping = defaultdict(list)
        for e in edges:
            for ind, subset in enumerate(contiguous_subsets):
                if subset.covers(e.data.subset):
                    edge_mapping[ind].append(e)
                    break
            else:
                raise ValueError(
                    "Failed to find contiguous subset for edge %s" % e.data)

        # Create transients for subsets and redirect edges
        for ind, subset in enumerate(contiguous_subsets):
            name, _ = sdfg.add_temp_transient(subset.size(), desc.dtype)
            anode = graph.add_access(name)
            graph.add_edge(map_entry, conn, anode, None,
                           Memlet(data=dname, subset=subset))
            for e in edge_mapping[ind]:
                graph.remove_edge(e)
                new_memlet = copy.deepcopy(e.data)
                new_edge = graph.add_edge(anode, None, e.dst, e.dst_conn,
                                          new_memlet)
                for pe in graph.memlet_tree(new_edge):
                    # Rename data on memlet
                    pe.data.data = name
                    # Offset memlets to match new transient
                    pe.data.subset.offset(subset, True)
