#include <vector>

class Q110 {
public:
    std::vector<int> subtractTwoArrays(const std::vector<int>& arrayA, const std::vector<int>& arrayB) {
        int n = arrayA.size();
        std::vector<int> result(n);
        for (int i = 0; i < n; ++i) {
            result[i] = arrayA[i] - arrayB[i];
        }
        return result;
    }
};
