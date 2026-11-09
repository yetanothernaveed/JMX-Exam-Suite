#include <cstdio>
#include <queue>
#include <vector>

int main() {
    // Input is provided in a file named input.txt inside the judging sandbox.
    if (!freopen("input.txt", "r", stdin)) {
        return 1;
    }

    int test_cases;
    if (scanf("%d", &test_cases) != 1) {
        return 0;
    }

    while (test_cases--) {
        int n, m;
        if (scanf("%d %d", &n, &m) != 2) {
            return 0;
        }

        std::vector<std::vector<int>> adjacency(n + 1);
        for (int edge = 0; edge < m; ++edge) {
            int u, v;
            if (scanf("%d %d", &u, &v) != 2) {
                return 0;
            }
            adjacency[u].push_back(v);
            adjacency[v].push_back(u);
        }

        std::vector<int> distance(n + 1, -1);
        std::vector<int> order;
        order.reserve(n);

        std::queue<int> queue;
        distance[1] = 0;
        queue.push(1);

        while (!queue.empty()) {
            int node = queue.front();
            queue.pop();
            order.push_back(node);

            for (int neighbour : adjacency[node]) {
                if (distance[neighbour] == -1) {
                    distance[neighbour] = distance[node] + 1;
                    queue.push(neighbour);
                }
            }
        }

        for (int i = 0; i < n; ++i) {
            if (i > 0) {
                putchar(' ');
            }
            printf("%d", order[i]);
        }
        putchar('\n');
    }

    return 0;
}
