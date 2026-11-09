import sys
from collections import deque


def main() -> None:
    # Input is provided in a file named input.txt inside the judging sandbox.
    with open("input.txt", "rb") as input_file:
        data = input_file.read()
    length = len(data)
    index = 0

    def next_int() -> int:
        nonlocal index
        while index < length and data[index] <= 32:
            index += 1
        value = 0
        while index < length and data[index] > 32:
            value = value * 10 + (data[index] - 48)
            index += 1
        return value

    test_cases = next_int()
    output: list[str] = []

    for _ in range(test_cases):
        n = next_int()
        m = next_int()

        adjacency: list[list[int]] = [[] for _ in range(n + 1)]
        for _ in range(m):
            u = next_int()
            v = next_int()
            adjacency[u].append(v)
            adjacency[v].append(u)

        distance = [-1] * (n + 1)
        distance[1] = 0
        queue = deque([1])
        order: list[int] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbour in adjacency[node]:
                if distance[neighbour] == -1:
                    distance[neighbour] = distance[node] + 1
                    queue.append(neighbour)

        output.append(" ".join(map(str, order)))

    sys.stdout.write("\n".join(output))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
