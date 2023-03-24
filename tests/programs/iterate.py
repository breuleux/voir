import sys

from voir import give, iterate

if __name__ == "__main__":
    for x in iterate(
        "things",
        range(10, 15),
        report_batch=bool(int(sys.argv[1])),
        ignore_loading=True,
    ):
        give(x=x)
