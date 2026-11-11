"""Flatten a nested settings dictionary into dotted keys."""

import collections

SETTINGS = {"db": {"host": "localhost", "port": 5432}, "debug": True}


def flatten(data, prefix=""):
    flat = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, collections.Mapping):
            flat.update(flatten(value, prefix=f"{name}."))
        else:
            flat[name] = value
    return flat


def main():
    print(flatten(SETTINGS))


if __name__ == "__main__":
    main()
