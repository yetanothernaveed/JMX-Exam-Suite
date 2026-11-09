class Q110 {
    int[] subtractTwoArrays(int[] A, int[] B) {
        int[] out = new int[A.length];

        for (int i = 0; i < A.length; i++) {
            out[i] = A[i] - B[i];
        }

        return out;
    }
}
