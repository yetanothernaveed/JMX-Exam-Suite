import java.io.*;
import java.util.*;

public class Main {
    public static void main(String[] args) {
        try (
            ByteScanner inputScanner = new ByteScanner(new FileInputStream("input.in"));
            ByteScanner outputScanner = new ByteScanner(new FileInputStream("expected.out"))
        ) {

            A userSolution = new A();

            int t = inputScanner.nextInt();

            int testCaseIndex = 0;

            while (t-- > 0) {
                int arraySize = inputScanner.nextInt();

                // Read Input Array A
                int[] arrayA = new int[arraySize];
                for (int i = 0; i < arraySize; i++) {
                    arrayA[i] = inputScanner.nextInt();
                }

                // Read Input Array B
                int[] arrayB = new int[arraySize];
                for (int i = 0; i < arraySize; i++) {
                    arrayB[i] = inputScanner.nextInt();
                }

                // Read Expected Array C
                int[] expectedArray = new int[arraySize];
                for (int i = 0; i < arraySize; i++) {
                    expectedArray[i] = outputScanner.nextInt();
                }

                // Measure execution time
                long startTime = System.nanoTime();
                int[] userResult = userSolution.addNums(arrayA, arrayB);
                long endTime = System.nanoTime();

                boolean isCorrect = compareArrays(userResult, expectedArray, arraySize);
                double executionTimeMs = (endTime - startTime) / 1_000_000.0;

                // Output JSON result line
                System.out.printf(Locale.US,
                    "{\"case\": %d, \"passed\": %b, \"time_ms\": %.2f}%n",
                    testCaseIndex + 1, isCorrect, executionTimeMs
                );
                System.out.flush();

                testCaseIndex++;
            }

        } catch (FileNotFoundException e) {
            System.err.println("FILE_ERROR: Could not locate expected.out file: " + e.getMessage());
            System.exit(1);
        } catch (Exception e) {
            e.printStackTrace(System.err);
            System.exit(1);
        }
    }

    private static boolean compareArrays(int[] actual, int[] expected, int expectedLength) {
        if (actual == null || actual.length != expectedLength) {
            return false;
        }
        for (int i = 0; i < expectedLength; i++) {
            if (actual[i] != expected[i]) {
                return false;
            }
        }
        return true;
    }
}

/**
 * High-performance Zero-Allocation Byte Scanner.
 * Parses ints directly from stream without creating String objects.
 */
class ByteScanner implements AutoCloseable {
    private final InputStream in;
    private final byte[] buffer = new byte[64 * 1024];
    private int head = 0;
    private int tail = 0;
    private int nextByte = -2; // -2 flags an empty single-byte lookahead buffer

    public ByteScanner(InputStream in) {
        this.in = in;
    }

    private int readByte() throws IOException {
        if (head >= tail) {
            head = 0;
            tail = in.read(buffer, 0, buffer.length);
            if (tail <= 0) return -1;
        }
        // FIX 1: Mask with 0xFF to prevent Java signed byte extension!
        return buffer[head++] & 0xFF; 
    }

    private int peekByte() throws IOException {
        if (nextByte == -2) {
            nextByte = readByte();
        }
        return nextByte;
    }

    private int getByte() throws IOException {
        int b = peekByte();
        nextByte = -2;
        return b;
    }

    public boolean hasNextInt() throws IOException {
        int c = peekByte();
        while (c != -1 && c <= ' ') {
            getByte();
            c = peekByte();
        }
        return c != -1;
    }

    public int nextInt() throws IOException {
        if (!hasNextInt()) {
            throw new NoSuchElementException("Unexpected EOF");
        }
        int c = getByte();
        boolean negative = false;
        if (c == '-') {
            negative = true;
            c = getByte();
        }

        // FIX 3: Accumulate as negative to prevent Integer.MIN_VALUE overflow
        int res = 0;
        while (c >= '0' && c <= '9') {
            res = res * 10 - (c - '0');
            c = getByte();
        }

        return negative ? res : -res;
    }

    @Override
    public void close() throws IOException {
        in.close();
    }
}
