class A {
    int[] addNums(int[] arr1, int[] arr2) {
        int[] out = new int[arr1.length];
        for (int i = 0; i < arr1.length; i++) {
            for (int j = 0; j < arr2.length; j++) {
                if (i == j) out[i] = arr1[i] + arr2[j];
            }
        }
        return out;
    }
}
