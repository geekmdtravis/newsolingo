"""CLI commands for managing Newsolingo configuration."""

from __future__ import annotations

import os
import subprocess
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from newsolingo.config import (
    CEFR_LEVELS,
    AppConfig,
    ensure_config_exists,
    get_xdg_config_path,
    load_config,
)

console = Console()


def config_show() -> int:
    """Display current configuration."""
    try:
        config = load_config()
        config_path = get_xdg_config_path()

        # Read raw YAML for display
        with open(config_path) as f:
            raw_yaml = f.read()

        console.print(
            Panel(
                f"[bold]Configuration file:[/bold] {config_path}", border_style="cyan"
            )
        )
        console.print()

        syntax = Syntax(raw_yaml, "yaml", theme="monokai", line_numbers=True)
        console.print(syntax)

        return 0
    except Exception as e:
        console.print(f"[red]Failed to load configuration: {e}[/red]")
        return 1


def config_set(key: str, value: str) -> int:
    """Set a configuration value using dot notation."""
    try:
        config_path = get_xdg_config_path()

        # Load existing config
        with open(config_path) as f:
            config_dict = yaml.safe_load(f) or {}

        # Navigate dot notation
        parts = key.split(".")
        current = config_dict

        # Navigate to parent dict
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            if not isinstance(current[part], dict):
                # Convert leaf to dict if needed
                current[part] = {}
            current = current[part]

        # Set value (try to parse as appropriate type)
        last_part = parts[-1]

        # Try to parse as int/float/bool
        parsed_value: Any
        if value.lower() in ("true", "false"):
            parsed_value = value.lower() == "true"
        elif value.isdigit():
            parsed_value = int(value)
        elif value.replace(".", "", 1).isdigit() and value.count(".") == 1:
            parsed_value = float(value)
        else:
            parsed_value = value

        current[last_part] = parsed_value

        # Validate by loading with Pydantic
        config = AppConfig(**config_dict)

        # Save back
        with open(config_path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)

        console.print(f"[green]Updated {key} = {repr(parsed_value)}[/green]")
        return 0

    except Exception as e:
        console.print(f"[red]Failed to set configuration: {e}[/red]")
        return 1


def config_add_language() -> int:
    """Interactive wizard to add a new language."""
    try:
        config_path = get_xdg_config_path()

        # Load existing config
        with open(config_path) as f:
            config_dict = yaml.safe_load(f) or {}

        if "languages" not in config_dict:
            config_dict["languages"] = {}

        console.print(
            Panel(
                "[bold]Add a new language[/bold]\n"
                "You'll need to provide:\n"
                "1. Language code (e.g., 'pt_br', 'es', 'fr')\n"
                "2. Display name\n"
                "3. CEFR level (pre-A1a, pre-A1b, A1, A2, B1, B2, C1, C2)\n"
                "4. Subjects (comma-separated topics)",
                border_style="cyan",
            )
        )

        # Get language code
        while True:
            code = console.input("\n[bold]Language code:[/bold] ").strip()
            if not code:
                console.print("[red]Language code is required[/red]")
                continue
            if code in config_dict["languages"]:
                console.print(f"[red]Language '{code}' already exists[/red]")
                continue
            break

        # Get display name
        name = console.input("[bold]Display name:[/bold] ").strip()
        if not name:
            name = code.replace("_", " ").title()

        # Get CEFR level
        while True:
            console.print("\n[bold]CEFR levels:[/bold]")
            for i, level in enumerate(CEFR_LEVELS, 1):
                console.print(f"  {i}. {level}")

            try:
                level_choice = console.input(
                    "\n[bold]Select level (1-7 or enter level):[/bold] "
                ).strip()
                if level_choice.isdigit():
                    idx = int(level_choice) - 1
                    if 0 <= idx < len(CEFR_LEVELS):
                        level = CEFR_LEVELS[idx]
                        break
                elif level_choice in CEFR_LEVELS:
                    level = level_choice
                    break
                console.print(
                    f"[red]Invalid level. Must be one of: {', '.join(CEFR_LEVELS)}[/red]"
                )
            except (ValueError, IndexError):
                console.print("[red]Invalid selection[/red]")

        # Get subjects
        subjects_input = console.input(
            "[bold]Subjects (comma-separated, e.g., 'linux,programming,geopolitics'):[/bold] "
        ).strip()
        subjects = [s.strip() for s in subjects_input.split(",") if s.strip()]
        if not subjects:
            subjects = ["linux", "programming", "geopolitics"]
            console.print(
                f"[yellow]Using default subjects: {', '.join(subjects)}[/yellow]"
            )

        # Add to config
        config_dict["languages"][code] = {
            "name": name,
            "level": level,
            "subjects": subjects,
        }

        # Validate
        config = AppConfig(**config_dict)

        # Save
        with open(config_path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)

        console.print(
            f"\n[green]Added language '{name}' ({code}) at level {level}[/green]"
        )
        console.print(f"Subjects: {', '.join(subjects)}")
        return 0

    except Exception as e:
        console.print(f"[red]Failed to add language: {e}[/red]")
        return 1


def config_edit() -> int:
    """Open configuration file in editor."""
    try:
        config_path = ensure_config_exists()
        editor = os.environ.get("EDITOR", "vi")

        console.print(f"[dim]Opening {config_path} with {editor}...[/dim]")
        subprocess.run([editor, config_path], check=True)

        # Validate after edit
        try:
            load_config()
            console.print("[green]Configuration is valid[/green]")
            return 0
        except Exception as e:
            console.print(f"[red]Configuration invalid after edit: {e}[/red]")
            console.print("[yellow]Please fix the errors and try again[/yellow]")
            return 1

    except Exception as e:
        console.print(f"[red]Failed to edit configuration: {e}[/red]")
        return 1
