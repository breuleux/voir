import json
import os
import sys

special_fd = int(os.environ.get("DATA_FD", 3))

if __name__ == "__main__":
    print("to stdout")
    print("to stderr", file=sys.stderr)
    with open(special_fd, "w", buffering=1) as lg:
        for i in range(5):
            print(json.dumps({"message": i}), file=lg)
        print("gargle gargle", file=lg)
    print("to stdout again")
