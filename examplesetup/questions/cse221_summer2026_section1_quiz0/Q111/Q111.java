import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.StringTokenizer;

public class Q111 {
    public static void main(String[] args) throws IOException {
        // Input is provided in a file named input.txt inside the judging sandbox.
        BufferedReader reader = new BufferedReader(new FileReader("input.txt"));
        PrintWriter out = new PrintWriter(System.out);

        StringTokenizer firstLine = new StringTokenizer(reader.readLine());
        int testCases = Integer.parseInt(firstLine.nextToken());

        for (int testCase = 0; testCase < testCases; testCase++) {
            StringTokenizer header = new StringTokenizer(reader.readLine());
            int n = Integer.parseInt(header.nextToken());
            int m = Integer.parseInt(header.nextToken());

            @SuppressWarnings("unchecked")
            ArrayList<Integer>[] adjacency = new ArrayList[n + 1];
            for (int node = 1; node <= n; node++) {
                adjacency[node] = new ArrayList<>();
            }

            for (int edge = 0; edge < m; edge++) {
                StringTokenizer endpoints = new StringTokenizer(reader.readLine());
                int u = Integer.parseInt(endpoints.nextToken());
                int v = Integer.parseInt(endpoints.nextToken());
                adjacency[u].add(v);
                adjacency[v].add(u);
            }

            int[] distance = new int[n + 1];
            Arrays.fill(distance, -1);
            distance[1] = 0;

            int[] queue = new int[n];
            int head = 0;
            int tail = 0;
            queue[tail++] = 1;

            for (int visited = 0; head < tail; visited++) {
                int node = queue[head++];
                if (visited > 0) {
                    out.print(' ');
                }
                out.print(node);

                for (int neighbour : adjacency[node]) {
                    if (distance[neighbour] == -1) {
                        distance[neighbour] = distance[node] + 1;
                        queue[tail++] = neighbour;
                    }
                }
            }
            out.println();
        }

        out.flush();
    }
}
