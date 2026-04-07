"""Entry point for running newsolingo as a module."""

import sys

from newsolingo.cli import run


def main() -> None:
    """Main entry point."""
    try:
        run()
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
