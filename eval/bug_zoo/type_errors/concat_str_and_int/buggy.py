"""Print a short inventory summary."""

INVENTORY = {"apples": 12, "pears": 7, "plums": 30}


def summary_line(name, count):
    return "We have " + count + " " + name


def main():
    for name, count in INVENTORY.items():
        print(summary_line(name, count))


if __name__ == "__main__":
    main()
