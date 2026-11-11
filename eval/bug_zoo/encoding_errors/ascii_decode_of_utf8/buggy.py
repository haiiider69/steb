"""Decode a response body received as raw bytes."""

RESPONSE_BODY = "Crème brûlée – 4.50 €".encode("utf-8")


def decode_body(body):
    return body.decode("ascii")


def main():
    print(decode_body(RESPONSE_BODY))


if __name__ == "__main__":
    main()
