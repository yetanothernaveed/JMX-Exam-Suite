#include <iostream>
#include <vector>
#include <fstream>

// Assume user solution implementation exists elsewhere or defined here
// class Q110 {
// public:
//     std::vector<int> subtractTwoArrays(const std::vector<int>& arrayA, const std::vector<int>& arrayB) {
//         int n = arrayA.size();
//         std::vector<int> result(n);
//         for (int i = 0; i < n; ++i) {
//             result[i] = arrayA[i] + arrayB[i];
//         }
//         return result;
//     }
// };

/*SUBMISSION_CODE*/

int main() {
    // Fast I/O optimization
    std::ios_base::sync_with_stdio(false);
    std::cin.tie(nullptr);

    // Redirect cin to read from "input.in"
    std::ifstream file("input.in");
    if (!file.is_open()) {
        std::cerr << "Failed to open input.in\n";
        return 1;
    }
    // Swap cin's buffer with the file buffer
    std::cin.rdbuf(file.rdbuf());

    Q110 userSolution;
    int t;
    if (!(std::cin >> t)) return 0;

    while (t--) {
        int arraySize;
        std::cin >> arraySize;

        std::vector<int> arrayA(arraySize);
        for (int i = 0; i < arraySize; ++i) {
            std::cin >> arrayA[i];
        }

        std::vector<int> arrayB(arraySize);
        for (int i = 0; i < arraySize; ++i) {
            std::cin >> arrayB[i];
        }

        std::vector<int> userResult = userSolution.subtractTwoArrays(arrayA, arrayB);

        if (!userResult.empty()) {
            std::cout << userResult[0];
            for (size_t i = 1; i < userResult.size(); ++i) {
                std::cout << ' ' << userResult[i];
            }
        }
        std::cout << '\n'; // Use '\n' instead of std::endl to avoid auto-flushing
    }

    return 0;
}
