"""Judge for Q111: accept any valid breadth-first traversal order.

A BFS may discover the neighbours of a city in any order, so a graph can have
many correct outputs. The testcase output file therefore stores the graph
itself (prefixed with ``#GRAPH``) instead of one hard-coded traversal. The
judge replays BFS over that graph and validates the submitted order exactly.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pistonjudge.src.Judge.base_judge import BaseJudge
from pistonjudge.src.Judge.local_harness import run_local
from pistonjudge.src.Judge.testcases import parse_int_row

GRAPH_SENTINEL = "#GRAPH"


@dataclass(repr=False)
class Graph:
    """An undirected graph stored in a testcase's metadata block."""

    n: int
    adjacency: list[list[int]]

    def __repr__(self) -> str:
        return f"<graph N={self.n}>"


@dataclass(repr=False)
class Order:
    """One submitted BFS traversal."""

    nodes: list[int]

    def __repr__(self) -> str:
        if len(self.nodes) <= 8:
            body = " ".join(map(str, self.nodes))
        else:
            body = " ".join(map(str, self.nodes[:8])) + " ..."
        return f"<BFS order length={len(self.nodes)}: {body}>"


def parse_graph(text: str) -> Graph:
    """Parse the ``#GRAPH`` metadata block written by the testcase generator."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != GRAPH_SENTINEL:
        raise ValueError("expected a #GRAPH metadata block")

    header = lines[1].split()
    if len(header) != 2:
        raise ValueError("graph header must contain N and M")
    n, m = int(header[0]), int(header[1])
    if n < 1:
        raise ValueError("N must be at least 1")

    edge_lines = lines[2:]
    if len(edge_lines) != m:
        raise ValueError(f"expected {m} edge lines, got {len(edge_lines)}")

    adjacency: list[list[int]] = [[] for _ in range(n + 1)]
    for line in edge_lines:
        parts = line.split()
        if len(parts) != 2:
            raise ValueError("each edge line must contain two endpoints")
        u, v = int(parts[0]), int(parts[1])
        if not (1 <= u <= n and 1 <= v <= n) or u == v:
            raise ValueError(f"invalid edge {u} {v}")
        adjacency[u].append(v)
        adjacency[v].append(u)
    return Graph(n=n, adjacency=adjacency)


def parse_order(text: str) -> Order:
    return Order(nodes=parse_int_row(text))


def is_valid_bfs_order(graph: Graph, order: list[int]) -> bool:
    """Return True iff ``order`` is producible by a FIFO breadth-first search.

    The check has two parts:

    1. Distances from city 1 are non-decreasing along the output.
    2. While processing the parents of depth ``d - 1`` in output order, each
       parent enqueues all of its not-yet-discovered depth-``d`` neighbours
       immediately. Those neighbours therefore have to form the next
       contiguous block of the depth-``d`` output, in any internal order.

    The second condition is what distinguishes a real BFS order from a mere
    "sorted by distance" order. For example, with edges 1-2, 1-3, 2-4, 3-5,
    the order ``1 2 3 5 4`` has non-decreasing distances and every node has an
    earlier parent, but it is impossible: processing 2 before 3 enqueues 4
    before 5.
    """
    n = graph.n
    if len(order) != n or not order or order[0] != 1:
        return False

    # The traversal must visit every city exactly once.
    seen = bytearray(n + 1)
    for node in order:
        if node < 1 or node > n or seen[node]:
            return False
        seen[node] = 1

    # Recompute the true BFS distances from city 1.
    distance = [-1] * (n + 1)
    distance[1] = 0
    queue = deque([1])
    while queue:
        node = queue.popleft()
        for neighbour in graph.adjacency[node]:
            if distance[neighbour] == -1:
                distance[neighbour] = distance[node] + 1
                queue.append(neighbour)

    if any(distance[node] == -1 for node in range(1, n + 1)):
        return False

    previous_distance = 0
    for node in order:
        current_distance = distance[node]
        if current_distance < previous_distance:
            return False
        previous_distance = current_distance

    max_distance = max(distance[1:])
    layers: list[list[int]] = [[] for _ in range(max_distance + 1)]
    for node in order:
        layers[distance[node]].append(node)

    assigned = bytearray(n + 1)
    for depth in range(1, max_distance + 1):
        parents = layers[depth - 1]
        children = layers[depth]
        child_index = 0

        for parent in parents:
            new_children = {
                neighbour
                for neighbour in graph.adjacency[parent]
                if distance[neighbour] == depth and not assigned[neighbour]
            }
            block_size = len(new_children)
            if child_index + block_size > len(children):
                return False

            block = children[child_index:child_index + block_size]
            if set(block) != new_children:
                return False

            for child in block:
                assigned[child] = 1
            child_index += block_size

        if child_index != len(children):
            return False

    return True


class Judge(BaseJudge):
    """Judge wrapper that parses graph metadata and validates BFS orders."""

    banned_keywords = ["sort", "process", "thread"]

    # Q111 submissions are complete programs that read a provided input file.
    input_file_name = "input.txt"

    def parse_result(self, text: str) -> Any:
        stripped = text.strip()
        if stripped.startswith(GRAPH_SENTINEL):
            return parse_graph(stripped)
        return parse_order(stripped)

    def compare_output(self, actual: Any, expected: Any) -> bool:
        if not isinstance(expected, Graph) or not isinstance(actual, Order):
            return False
        try:
            return is_valid_bfs_order(expected, actual.nodes)
        except (IndexError, TypeError, ValueError):
            return False


if __name__ == "__main__":
    run_local(
        Judge,
        Path(__file__).resolve().parents[1],
        default_language="python",
    )
