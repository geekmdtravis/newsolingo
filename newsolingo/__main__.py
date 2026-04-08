"""Entry point for running newsolingo as a module."""

import argparse
import sys

from newsolingo.storage.database import DEFAULT_DB_PATH, Database


def confirm_reset() -> bool:
    """Ask for confirmation before deleting database."""
    print("\nWARNING: This will delete all database files at:")
    print(f"  {DEFAULT_DB_PATH}")
    print("  (and associated -shm, -wal, .bak, .corrupted files)")
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
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    # Legacy flag for backward compatibility
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Delete the database and all its files, then exit (deprecated, use 'run --reset-db')",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command (default)
    run_parser = subparsers.add_parser(
        "run",
        help="Run an interactive session (default)",
    )
    run_parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Delete the database and all its files, then exit",
    )
    run_parser.add_argument(
        "--url",
        type=str,
        help="Direct URL to scrape for article (requires --language)",
    )
    run_parser.add_argument(
        "--language",
        type=str,
        help="Language code (e.g., pt_br) to skip interactive selection; required when using --url",
    )
    run_parser.add_argument(
        "--subject",
        type=str,
        default="Direct",
        help="Subject to skip interactive selection; for direct URL articles, default is 'Direct'",
    )
    run_parser.add_argument(
        "--permissive",
        action="store_true",
        help="Accept missing accents/transliteration; if not specified, you'll be asked interactively.",
    )

    # Config command
    config_parser = subparsers.add_parser(
        "config",
        help="Manage configuration",
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_command",
        help="Configuration subcommands",
    )

    # Config show
    config_subparsers.add_parser(
        "show",
        help="Display current configuration",
    )

    # Config set
    set_parser = config_subparsers.add_parser(
        "set",
        help="Set a configuration value",
    )
    set_parser.add_argument(
        "key",
        help="Configuration key using dot notation (e.g., 'user.name', 'llm.provider')",
    )
    set_parser.add_argument(
        "value",
        help="Value to set",
    )

    # Config add-language
    config_subparsers.add_parser(
        "add-language",
        help="Interactive wizard to add a new language",
    )

    # Config edit
    config_subparsers.add_parser(
        "edit",
        help="Edit configuration file with $EDITOR",
    )

    # Session command
    session_parser = subparsers.add_parser(
        "session",
        help="Manage and review saved sessions",
    )
    session_subparsers = session_parser.add_subparsers(
        dest="session_command",
        help="Session subcommands",
    )

    # Session list
    session_subparsers.add_parser(
        "list",
        help="List saved sessions",
    )

    # Session chat
    chat_parser = session_subparsers.add_parser(
        "chat",
        help="Start interactive chat about a saved session",
    )
    chat_parser.add_argument(
        "session_id",
        type=int,
        help="Session ID or filename (from 'session list')",
    )

    args = parser.parse_args()

    # Validate URL/language combination
    if (
        hasattr(args, "url")
        and getattr(args, "url", None)
        and not getattr(args, "language", None)
    ):
        parser.error("--url requires --language to be specified")

    # Check for invalid combination of --reset-db with subcommands
    if args.reset_db and args.command and args.command != "run":
        parser.error(
            "--reset-db can only be used with 'run' command or with no command"
        )

    # Handle --reset-db as a legacy top-level flag (for backward compatibility)
    # but only if no command specified
    if not args.command and hasattr(args, "reset_db") and args.reset_db:
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

    # Handle config subcommands
    if args.command == "config":
        try:
            from newsolingo.config_cli import (
                config_add_language,
                config_edit,
                config_set,
                config_show,
            )
        except ImportError as e:
            print(f"Failed to import config module: {e}")
            sys.exit(1)

        if args.config_command == "show":
            sys.exit(config_show())
        elif args.config_command == "set":
            sys.exit(config_set(args.key, args.value))
        elif args.config_command == "add-language":
            sys.exit(config_add_language())
        elif args.config_command == "edit":
            sys.exit(config_edit())
        else:
            config_parser.print_help()
            sys.exit(1)

    # Handle session subcommands
    if args.command == "session":
        try:
            from newsolingo.config import load_config
            from newsolingo.llm.client import LLMClient
            from newsolingo.review.chat import interactive_chat
            from newsolingo.storage.session_export import (
                list_sessions,
                load_session_markdown,
            )
        except ImportError as e:
            print(f"Failed to import session module: {e}")
            sys.exit(1)

        if args.session_command == "list":
            sessions = list_sessions()
            if not sessions:
                print("No saved sessions found.")
                sys.exit(0)

            print(f"Found {len(sessions)} saved sessions:\n")
            for i, sess in enumerate(sessions, 1):
                print(f"{i}. Session {sess.get('id', '?')}")
                print(f"   Language: {sess.get('language_code', 'Unknown')}")
                print(f"   Level: {sess.get('level', 'Unknown')}")
                print(f"   Score: {sess.get('overall_score', 0):.1f}/100")
                print(f"   Date: {sess.get('created_at', 'Unknown')}")
                print(f"   File: {sess.get('filename', 'Unknown')}")
                print()
            sys.exit(0)

        elif args.session_command == "chat":
            if not args.session_id:
                print("Error: session_id required")
                session_parser.print_help()
                sys.exit(1)

            # Load config and LLM client
            try:
                config = load_config()
                llm_client = LLMClient(config)
                # Verify LLM health
                health = llm_client.health_check()
                if not health["ok"]:
                    print(f"LLM server is not reachable: {health['error']}")
                    sys.exit(1)
            except Exception as e:
                print(f"Failed to initialize LLM: {e}")
                sys.exit(1)

            # Load session markdown
            markdown = load_session_markdown(args.session_id)
            if not markdown:
                print(f"Session {args.session_id} not found.")
                sys.exit(1)

            # Start interactive chat
            try:
                interactive_chat(markdown, llm_client, config, args.session_id)
                sys.exit(0)
            except KeyboardInterrupt:
                print("\nChat interrupted.")
                sys.exit(0)
            except Exception as e:
                print(f"Error during chat: {e}")
                sys.exit(1)

        else:
            session_parser.print_help()
            sys.exit(1)

    # Handle run command (or default)
    if args.command is None or args.command == "run":
        # Normal session flow
        # Import cli only when needed to avoid unnecessary dependencies
        try:
            from newsolingo.cli import run
        except ImportError as e:
            print(f"Failed to import CLI module: {e}")
            print("Make sure all dependencies are installed (pip install -e .)")
            sys.exit(1)

        # Handle --reset-db within run command
        if hasattr(args, "reset_db") and args.reset_db:
            if confirm_reset():
                deleted = Database.delete_database_files(DEFAULT_DB_PATH)
                if deleted:
                    print(f"Deleted {len(deleted)} files:")
                    for f in deleted:
                        print(f"  {f}")
                else:
                    print("No database files found (already clean).")
                sys.exit(0)
            else:
                print("Reset cancelled.")
                sys.exit(0)

        try:
            run(
                verbose=args.verbose,
                url=getattr(args, "url", None),
                language=getattr(args, "language", None),
                subject=getattr(args, "subject", None),
                ignore_accents=getattr(args, "permissive", None),
            )
            sys.exit(0)
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
