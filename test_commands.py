"""Test the command dispatcher."""
import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")

from commands.registry import parse_and_dispatch


def run(text: str):
    print()
    print("=" * 70)
    print(f"> {text}")
    print("=" * 70)
    result = parse_and_dispatch(text)
    if result is None:
        print("(not a command)")
    else:
        print(result.text)
        if result.is_error:
            print("[ERROR]")


def main():
    run("/help")
    run("/skills")
    run("/search memory forensics")
    run("/search web scraper")
    run("/skill analyzing-memory-dumps-with-volatility")
    run("/categories")
    run("/status")
    run("/unknown-command")
    run("just normal text")


if __name__ == "__main__":
    main()