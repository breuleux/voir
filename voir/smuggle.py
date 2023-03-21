import re
from collections import deque

oldhex = "0123456789abcdef"
newhex = "0123456789:;<=>?"

hexsub = dict(zip(oldhex, newhex))
hexsub_back = dict(zip(newhex, oldhex))


def encode_control(s):
    encoded = "".join([hexsub[c] for c in s.encode("utf8").hex()])
    return f"\033[{encoded}z"


def decode_control(s):
    s = s[2:-1]
    decoded_hex = "".join([hexsub_back[c] for c in s])
    return bytes.fromhex(decoded_hex).decode("utf8")


def decode_control_stream(s):
    pass


class SmuggleWriter:
    def __init__(self, stream):
        self.stream = stream

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, typ=None, exc=None, tb=None):
        self.stream.__exit__(typ, exc, tb)
        return self

    def write(self, txt):
        return self.stream.write(encode_control(txt))

    def flush(self):
        return self.stream.flush()

    def close(self):
        return self.stream.close()


class LineAccumulator:
    def __init__(self):
        self.lines = deque()
        self.current = ""

    def process(self, char):
        self.current += char
        if char == "\n":
            self.lines.append(self.current)
            self.current = ""


class Decoder:
    def __init__(self, principal):
        self.principal = principal
        self.out = LineAccumulator()
        self.data = LineAccumulator()
        self.code = ""
        self.coding = False

    def endcode(self):
        self.coding = False
        if re.match(string=self.code, pattern="\033\\[[0-9:;<=>?]*z"):
            for char in decode_control(self.code):
                self.data.process(char)
        else:
            self.out.current += self.code
        self.code = ""

    def process_char(self, char):
        if self.coding:
            if ord(char) < 0x20:
                self.out.process(char)
                self.endcode()
            elif ord(char) >= 0x40 and char != "[":
                self.code += char
                self.endcode()
            else:
                self.code += char

        elif char == "\033":
            self.coding = True
            self.code += char

        else:
            self.out.process(char)

    def getline(self, which):
        if which == "out":
            if self.out.lines:
                return self.out.lines.popleft()
        elif which == "data":
            if self.data.lines:
                return self.data.lines.popleft()
        return None

    def readline(self, which):
        while (result := self.getline(which)) is None:
            nxt = self.principal.read(1)
            if not nxt:
                return None
            self.process_char(nxt.decode("utf8"))
        return result


class MultimodalFile:
    def __init__(self, decoder, which, name):
        self.name = name
        self.decoder = decoder
        self.which = which

    def fileno(self):
        return self.name

    def readline(self):
        zazz = self.decoder.readline(self.which)
        # print(zazz, self.decoder.principal)
        return zazz
