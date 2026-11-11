"""Turn article titles into URL slugs."""

import re

TITLES = ["Hello, World!", "Seen this error before?", "  Spaces   everywhere  "]


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def main():
    for title in TITLES:
        print(slugify(title))


if __name__ == "__main__":
    main()
