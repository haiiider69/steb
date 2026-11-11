"""Build a database connection string from a JSON settings document."""

import json

RAW_SETTINGS = '{"host": "localhost", "port": 5432, "name": "inventory"}'


def load_settings(raw):
    return json.loads(raw)


def connection_string(settings):
    user = settings.get("user", "postgres")
    return f"postgresql://{user}@{settings['host']}:{settings['port']}/{settings['name']}"


def main():
    settings = load_settings(RAW_SETTINGS)
    print(connection_string(settings))


if __name__ == "__main__":
    main()
