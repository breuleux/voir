from giving import give


def main():
    for n in range(3):
        give(n)

    give(m=44)
    give(n=100)

    print("done")


if __name__ == "__main__":
    main()
