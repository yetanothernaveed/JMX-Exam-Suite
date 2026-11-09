"""Offline tests for the Q111 BFS-order validator.

Run from the repository's ``server`` directory so that the ``pistonjudge``
package resolves, for example:

    cd server
    python3 ../examplesetup/questions/cse221_summer2026_section1_quiz0/Q111/~judge/test_Q111Judge.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from Q111Judge import Graph, is_valid_bfs_order, parse_graph, parse_order


def make_graph(n: int, edges: list[tuple[int, int]]) -> Graph:
    adjacency: list[list[int]] = [[] for _ in range(n + 1)]
    for u, v in edges:
        adjacency[u].append(v)
        adjacency[v].append(u)
    return Graph(n=n, adjacency=adjacency)


class TestValidBfsOrder(unittest.TestCase):
    def test_single_city(self):
        self.assertTrue(is_valid_bfs_order(make_graph(1, []), [1]))

    def test_line_has_one_order(self):
        graph = make_graph(5, [(1, 2), (2, 3), (3, 4), (4, 5)])
        self.assertTrue(is_valid_bfs_order(graph, [1, 2, 3, 4, 5]))
        self.assertFalse(is_valid_bfs_order(graph, [1, 2, 4, 3, 5]))
        self.assertFalse(is_valid_bfs_order(graph, [1, 3, 2, 4, 5]))

    def test_star_all_leaf_permutations_are_valid(self):
        graph = make_graph(6, [(1, leaf) for leaf in range(2, 7)])
        self.assertTrue(is_valid_bfs_order(graph, [1, 2, 3, 4, 5, 6]))
        self.assertTrue(is_valid_bfs_order(graph, [1, 6, 4, 2, 5, 3]))

    def test_complete_graph_any_permutation_after_source(self):
        n = 5
        graph = make_graph(
            n,
            [(u, v) for u in range(1, n + 1) for v in range(u + 1, n + 1)],
        )
        self.assertTrue(is_valid_bfs_order(graph, [1, 5, 4, 3, 2]))
        self.assertTrue(is_valid_bfs_order(graph, [1, 2, 3, 4, 5]))

    def test_block_partition_is_enforced(self):
        # Layer 1: 2, 3. Layer 2: 4 (child of 2), 5 (child of 3).
        graph = make_graph(5, [(1, 2), (1, 3), (2, 4), (3, 5)])
        # Processing 2 before 3 must enqueue 4 before 5.
        self.assertTrue(is_valid_bfs_order(graph, [1, 2, 3, 4, 5]))
        self.assertTrue(is_valid_bfs_order(graph, [1, 3, 2, 5, 4]))
        # These are distance-monotonic but impossible for a real BFS.
        self.assertFalse(is_valid_bfs_order(graph, [1, 2, 3, 5, 4]))
        self.assertFalse(is_valid_bfs_order(graph, [1, 3, 2, 4, 5]))

    def test_shared_child_belongs_to_first_parent_that_discovers_it(self):
        # Both 2 and 3 reach 4; 5 is reached only by 3.
        graph = make_graph(5, [(1, 2), (1, 3), (2, 4), (3, 4), (3, 5)])
        # 2 goes first, so 4 is in 2's block and 5 follows in 3's block.
        self.assertTrue(is_valid_bfs_order(graph, [1, 2, 3, 4, 5]))
        # If 3 goes first it discovers both 4 and 5.
        self.assertTrue(is_valid_bfs_order(graph, [1, 3, 2, 4, 5]))
        self.assertTrue(is_valid_bfs_order(graph, [1, 3, 2, 5, 4]))
        # 2 before 3 cannot leave 4 for 3.
        self.assertFalse(is_valid_bfs_order(graph, [1, 2, 3, 5, 4]))

    def test_rejects_bad_permutations(self):
        graph = make_graph(3, [(1, 2), (2, 3)])
        self.assertFalse(is_valid_bfs_order(graph, [1, 2, 2]))
        self.assertFalse(is_valid_bfs_order(graph, [1, 2]))
        self.assertFalse(is_valid_bfs_order(graph, [0, 1, 2, 3]))
        self.assertFalse(is_valid_bfs_order(graph, [2, 1, 3]))

    def test_rejects_decreasing_distance(self):
        graph = make_graph(4, [(1, 2), (2, 3), (2, 4)])
        self.assertFalse(is_valid_bfs_order(graph, [1, 3, 2, 4]))


class TestParsing(unittest.TestCase):
    def test_parse_graph_and_order(self):
        graph = parse_graph(
            "#GRAPH\n3 2\n1 2\n2 3\n"
        )
        self.assertEqual(graph.n, 3)
        self.assertEqual(graph.adjacency[1], [2])
        self.assertEqual(graph.adjacency[2], [1, 3])
        self.assertEqual(graph.adjacency[3], [2])

        order = parse_order("1 2 3\n")
        self.assertEqual(order.nodes, [1, 2, 3])

    def test_malformed_graph_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_graph("#GRAPH\n3 3\n1 2\n")
        with self.assertRaises(ValueError):
            parse_graph("#GRAPH\n3 1\n1 1\n")
        with self.assertRaises(ValueError):
            parse_graph("3 1\n1 2\n")


if __name__ == "__main__":
    unittest.main()
