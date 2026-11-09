import java.io.*;
import java.util.*;

public class Main {
    public static void main(String[] args) {
        // Use custom Fast I/O for both reading the file and writing to stdout
        try (FileInputStream fis = new FileInputStream("input.in");
             ByteScanner scanner = new ByteScanner(fis);
             ByteWriter out = new ByteWriter(System.out)) {

            Q110 userSolution = new Q110();

            int t = scanner.nextInt();

            while (t-- > 0) {
                int arraySize = scanner.nextInt();

                // Read Input Array A
                int[] arrayA = new int[arraySize];
                for (int i = 0; i < arraySize; i++) {
                    arrayA[i] = scanner.nextInt();
                }

                // Read Input Array B
                int[] arrayB = new int[arraySize];
                for (int i = 0; i < arraySize; i++) {
                    arrayB[i] = scanner.nextInt();
                }

                // Compute the result
                int[] userResult = userSolution.subtractTwoArrays(arrayA, arrayB);

                // Write the resulting array strictly avoiding String allocations
                if (userResult != null && userResult.length > 0) {
                    out.print(userResult[0]);
                    for (int i = 1; i < userResult.length; i++) {
                        out.printSpace();
                        out.print(userResult[i]);
                    }
                }
                out.println();
            }

        } catch (Exception e) {
            e.printStackTrace(System.err);
            System.exit(1);
        }
    }
}

/**
 * Flattened Zero-Allocation Byte Scanner.
 * Method calls inside the parsing loop are removed for max speed.
 */
class ByteScanner implements AutoCloseable {
    private final InputStream in;
    private final byte[] buffer = new byte[1 << 16]; // 64KB Buffer
    private int head = 0;
    private int tail = 0;

    public ByteScanner(InputStream in) {
        this.in = in;
    }

    private byte read() throws IOException {
        if (head >= tail) {
            head = 0;
            tail = in.read(buffer, 0, buffer.length);
            if (tail <= 0) return -1; // EOF
        }
        return buffer[head++];
    }

    public int nextInt() throws IOException {
        byte c = read();
        while (c <= ' ') {
            if (c == -1) throw new NoSuchElementException("Unexpected EOF");
            c = read();
        }
        boolean negative = false;
        if (c == '-') {
            negative = true;
            c = read();
        }
        int res = 0;
        do {
            res = res * 10 + (c - '0');
            c = read();
        } while (c > ' ');
        
        return negative ? -res : res;
    }

    @Override
    public void close() throws IOException {
        in.close();
    }
}

/**
 * High-performance Zero-Allocation Byte Writer.
 * Writes ints directly to a byte buffer bypassing String concatenation.
 */
class ByteWriter implements AutoCloseable {
    private final OutputStream out;
    private final byte[] buffer = new byte[1 << 16]; // 64KB Buffer
    private int pos = 0;
    private final byte[] charBuf = new byte[12]; // Temporary buffer for int parsing

    public ByteWriter(OutputStream out) {
        this.out = out;
    }

    public void print(int n) throws IOException {
        if (n == 0) {
            writeByte((byte) '0');
            return;
        }
        if (n == Integer.MIN_VALUE) {
            writeBytes("-2147483648".getBytes());
            return;
        }
        if (n < 0) {
            writeByte((byte) '-');
            n = -n;
        }
        
        int p = 12;
        while (n > 0) {
            charBuf[--p] = (byte) ('0' + (n % 10));
            n /= 10;
        }
        for (; p < 12; p++) {
            writeByte(charBuf[p]);
        }
    }

    public void printSpace() throws IOException {
        writeByte((byte) ' ');
    }

    public void println() throws IOException {
        writeByte((byte) '\n');
    }

    private void writeByte(byte b) throws IOException {
        if (pos == buffer.length) flush();
        buffer[pos++] = b;
    }

    private void writeBytes(byte[] b) throws IOException {
        for (byte value : b) writeByte(value);
    }

    public void flush() throws IOException {
        if (pos > 0) {
            out.write(buffer, 0, pos);
            pos = 0;
        }
    }

    @Override
    public void close() throws IOException {
        flush();
        out.close();
    }
}

/*SUBMISSION_CODE*/
