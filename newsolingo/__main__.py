"""Entry point for running newsolingo as a module."""

import argparse
import sys
from pathlib import Path

from newsolingo.storage.database import DEFAULT_DB_PATH, Database


def confirm_reset() -> bool:
    """Ask for confirmation before deleting database."""
    print(f"\nWARNING: This will delete all database files at:")
    print(f"  {DEFAULT_DB_PATH}")
    print(f"  (and associated -shm, -wal, .bak, .corrupted files)")
    print()
    try:
        response = (
            input("Are you sure you want to reset the database? [y/N]: ")
            .strip()
            .lower()
        )
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Newsolingo - Language learning with real-world articles"
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Delete the database and all its files, then exit",
    )
    args = parser.parse_args()

    if args.reset_db:
        if confirm_reset():
            deleted = Database.delete_database_files(DEFAULT_DB_PATH)
            if deleted:
                print(f"Deleted {len(deleted)} files:")
                for f in deleted:
                    print(f"  {f}")
            else:
                print("No database files found (already clean).")
        else:
            print("Reset cancelled.")
        sys.exit(0)

    # Normal session flow
    # Import cli only when needed to avoid unnecessary dependencies
    try:
        from newsolingo.cli import run
    except ImportError as e:
        print(f"Failed to import CLI module: {e}")
        print("Make sure all dependencies are installed (pip install -e .)")
        sys.exit(1)

    try:
        run()
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
