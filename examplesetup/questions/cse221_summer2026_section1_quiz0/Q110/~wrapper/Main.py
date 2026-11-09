import sys

class ByteScanner:
    def __init__(self, file_obj):
        self.file_obj = file_obj
        self.buffer = bytearray(64 * 1024)
        self.head = 0
        self.tail = 0
        self.next_byte = -2

    def read_byte(self):
        if self.head >= self.tail:
            self.head = 0
            chunk = self.file_obj.read(64 * 1024)
            self.tail = len(chunk)
            if self.tail <= 0:
                return -1
            self.buffer[:self.tail] = chunk
        
        b = self.buffer[self.head] & 0xFF
        self.head += 1
        return b

    def peek_byte(self):
        if self.next_byte == -2:
            self.next_byte = self.read_byte()
        return self.next_byte

    def get_byte(self):
        b = self.peek_byte()
        self.next_byte = -2
        return b

    def has_next_int(self):
        c = self.peek_byte()
        while c != -1 and c <= 32:  # 32 is space (' ')
            self.get_byte()
            c = self.peek_byte()
        return c != -1

    def next_int(self):
        if not self.has_next_int():
            raise Exception("Unexpected EOF")
        
        c = self.get_byte()
        negative = False
        if c == 45:  # '-'
            negative = True
            c = self.get_byte()

        res = 0
        while 48 <= c <= 57:  # '0' to '9'
            res = res * 10 - (c - 48)
            c = self.get_byte()

        return res if negative else -res

    def close(self):
        self.file_obj.close()


/*SUBMISSION_CODE*/


def main():
    try:
        with open("input.in", "rb") as fin:
            input_scanner = ByteScanner(fin)
            user_solution = Q110()

            t = input_scanner.next_int()

            while t > 0:
                t -= 1
                array_size = input_scanner.next_int()

                # Read Input Array A
                array_a = [0] * array_size
                for i in range(array_size):
                    array_a[i] = input_scanner.next_int()

                # Read Input Array B
                array_b = [0] * array_size
                for i in range(array_size):
                    array_b[i] = input_scanner.next_int()

                # Compute the result
                user_result = user_solution.subtractTwoArrays(array_a, array_b)

                # Write output to stdout immediately for each testcase
                if user_result:
                    sys.stdout.write(" ".join(map(str, user_result)))
                sys.stdout.write("\n")

                sys.stdout.flush()

    except FileNotFoundError as e:
        sys.stderr.write("FILE_ERROR: Could not locate input.in file: " + str(e) + "\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
