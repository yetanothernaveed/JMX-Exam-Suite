"""Generate testcases for Q111.

``tc.in`` uses the judge's ``@@CASE-n`` framing so every case can be parsed
separately. ``input.txt`` is the plain file that submissions read inside the
sandbox:

    T
    N M
    u v
    ...

    N M
    ...

Each case in ``tc.out`` repeats the graph inside a ``#GRAPH`` metadata block,
framed with ``@@CASE-n`` markers. The judge needs the graph, not a single
expected traversal, because many different BFS orders can be correct for the
same graph.
"""

import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def random_connected_graph(
    n: int,
    m: int,
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Return a random connected simple graph with exactly ``n`` nodes and ``m`` edges."""
    if n < 1:
        raise ValueError("n must be positive")
    max_edges = n * (n - 1) // 2
    if not (n - 1 <= m <= max_edges):
        raise ValueError(f"cannot build a connected graph with n={n}, m={m}")

    edges: set[tuple[int, int]] = set()

    # A random spanning tree guarantees connectivity.
    for node in range(2, n + 1):
        parent = rng.randint(1, node - 1)
        edges.add((parent, node))

    # Add random non-duplicate edges until the requested count is reached.
    while len(edges) < m:
        u = rng.randint(1, n)
        v = rng.randint(1, n)
        if u == v:
            continue
        if u > v:
            u, v = v, u
        edges.add((u, v))

    result = list(edges)
    rng.shuffle(result)
    return result


def validate_edges(n: int, edges: list[tuple[int, int]]) -> None:
    """Sanity-check the constraints the problem promises."""
    if len(set(edges)) != len(edges):
        raise AssertionError("duplicate edge")

    adjacency: list[list[int]] = [[] for _ in range(n + 1)]
    for u, v in edges:
        if not (1 <= u <= n and 1 <= v <= n):
            raise AssertionError(f"endpoint out of range: {u} {v}")
        if u == v:
            raise AssertionError(f"self-loop: {u} {v}")
        adjacency[u].append(v)
        adjacency[v].append(u)

    if n == 1:
        if edges:
            raise AssertionError("a one-node graph must have no edges")
        return

    seen = bytearray(n + 1)
    seen[1] = 1
    stack = [1]
    reached = 1
    while stack:
        node = stack.pop()
        for neighbour in adjacency[node]:
            if not seen[neighbour]:
                seen[neighbour] = 1
                reached += 1
                stack.append(neighbour)

    if reached != n:
        raise AssertionError("graph is not connected")


def build_cases(rng: random.Random) -> list[tuple[int, list[tuple[int, int]]]]:
    """Return ``(n, edges)`` pairs in increasing order of difficulty."""
    line_size = 200_000
    random_size = 200_000
    random_edges = 300_000

    line_edges = [(i, i + 1) for i in range(1, line_size)]
    rng.shuffle(line_edges)

    complete_size = 8
    complete_edges = [
        (u, v)
        for u in range(1, complete_size + 1)
        for v in range(u + 1, complete_size + 1)
    ]

    return [
        # A single city with no roads.
        (1, []),
        # The smallest non-trivial graph.
        (2, [(1, 2)]),
        # A path: exactly one valid BFS order.
        (5, [(1, 2), (2, 3), (3, 4), (4, 5)]),
        # A star: any permutation of the leaves is valid.
        (6, [(1, leaf) for leaf in range(2, 7)]),
        # A cycle: two directions are possible.
        (6, [(i, i + 1) for i in range(1, 6)] + [(6, 1)]),
        # Two layer-1 parents with separate layer-2 children. This rejects
        # distance-monotonic orders that a real FIFO BFS cannot produce.
        (5, [(1, 2), (1, 3), (2, 4), (3, 5)]),
        # A complete graph: every permutation after city 1 is valid.
        (complete_size, complete_edges),
        # A medium random graph with many valid orders.
        (1000, random_connected_graph(1000, 2000, rng)),
        # A large path, to exercise time and memory limits.
        (line_size, line_edges),
        # A large random graph at the maximum edge count.
        (random_size, random_connected_graph(random_size, random_edges, rng)),
    ]


def generate(seed: int = 221) -> None:
    rng = random.Random(seed)
    cases = build_cases(rng)

    input_path = BASE_DIR / "tc.in"
    user_input_path = BASE_DIR / "input.txt"
    output_path = BASE_DIR / "tc.out"

    with input_path.open("w", encoding="utf-8") as input_file, \
            user_input_path.open("w", encoding="utf-8") as user_input_file, \
            output_path.open("w", encoding="utf-8") as output_file:
        user_input_file.write(f"{len(cases)}\n")
        for number, (n, edges) in enumerate(cases, start=1):
            validate_edges(n, edges)

            edge_text = "".join(f"{u} {v}\n" for u, v in edges)
            header = f"{n} {len(edges)}\n"

            input_file.write(f"@@CASE-{number}\n{header}{edge_text}")
            user_input_file.write(f"{header}{edge_text}")
            output_file.write(f"@@CASE-{number}\n#GRAPH\n{header}{edge_text}")

    total_n = sum(n for n, _ in cases)
    total_m = sum(len(edges) for _, edges in cases)
    print(
        f"Wrote {len(cases)} cases to {input_path}, {user_input_path}, and "
        f"{output_path} (sum N={total_n}, sum M={total_m})."
    )


if __name__ == "__main__":
    generate()
