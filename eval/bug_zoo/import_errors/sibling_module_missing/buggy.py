"""Turn article titles into URL slugs."""

from text_tools import slugify

TITLES = ["Hello, World!", "Seen this error before?", "  Spaces   everywhere  "]


def main():
    for title in TITLES:
        print(slugify(title))


if __name__ == "__main__":
    main()
