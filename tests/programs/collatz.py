import argparse


def collatz(n):
    while n != 1:
        print(n)
        n = (3 * n + 1) if n % 2 else (n // 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n")
    options = parser.parse_args()
    collatz(int(options.n))


if __name__ == "__main__":
    main()
