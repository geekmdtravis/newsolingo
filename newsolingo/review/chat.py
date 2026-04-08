"""Interactive chat for reviewing saved sessions."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel

from newsolingo.config import AppConfig
from newsolingo.llm.client import LLMClient
from newsolingo.storage.session_export import get_sessions_dir

logger = logging.getLogger(__name__)
console = Console()


def _truncate_text_to_tokens(
    text: str, max_tokens: int, chars_per_token: int = 4
) -> str:
    """Truncate text to approximately fit within token limit.

    Args:
        text: Text to truncate
        max_tokens: Maximum number of tokens
        chars_per_token: Approximate characters per token (conservative estimate)

    Returns:
        Truncated text with ellipsis if needed
    """
    max_chars = max_tokens * chars_per_token
    if len(text) <= max_chars:
        return text

    # Try to truncate at sentence boundary
    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    last_newline = truncated.rfind("\n")
    cutoff = max(last_period, last_newline)

    if cutoff > max_chars * 0.8:  # If we found a reasonable cutoff
        return truncated[: cutoff + 1] + "\n\n[Content truncated due to length...]"
    else:
        return truncated + "\n\n[Content truncated due to length...]"


def _extract_frontmatter(markdown: str) -> dict[str, Any]:
    """Extract YAML frontmatter from session markdown."""
    frontmatter = {}

    # Find YAML frontmatter between --- markers
    frontmatter_re = re.compile(r"^---\n(.*?)\n---", re.DOTALL | re.MULTILINE)
    match = frontmatter_re.match(markdown)
    if not match:
        return frontmatter

    yaml_content = match.group(1)
    yaml_line_re = re.compile(r"^([^:]+):\s*(.*)$")

    for line in yaml_content.split("\n"):
        line = line.strip()
        if not line:
            continue
        line_match = yaml_line_re.match(line)
        if line_match:
            key = line_match.group(1).strip()
            value = line_match.group(2).strip()

            # Parse simple types
            if value.lower() in ("true", "false"):
                frontmatter[key] = value.lower() == "true"
            elif value.isdigit():
                frontmatter[key] = int(value)
            elif value.replace(".", "", 1).isdigit() and value.count(".") == 1:
                frontmatter[key] = float(value)
            elif value.startswith('"') and value.endswith('"'):
                frontmatter[key] = value[1:-1].replace('\\"', '"').replace("\\n", "\n")
            else:
                frontmatter[key] = value

    return frontmatter


def _save_chat_log(
    session_markdown: str, conversation: list[tuple[str, str]], session_id: int | str
) -> Path:
    """Save chat conversation to a file."""
    sessions_dir = get_sessions_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = sessions_dir / f"session_{session_id}_chat_{timestamp}.md"

    # Extract session metadata
    frontmatter = _extract_frontmatter(session_markdown)

    # Build log content
    lines = ["---"]
    lines.append(f"session_id: {session_id}")
    lines.append(f"chat_started: {datetime.now().isoformat()}")
    for key, value in frontmatter.items():
        if key not in ("id", "created_at"):
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Chat Review - Session {session_id}")
    lines.append("")

    # Add conversation
    lines.append("## Conversation")
    lines.append("")

    for i, (role, message) in enumerate(conversation, 1):
        lines.append(f"### {role.capitalize()} {i}")
        lines.append("")
        lines.append(message)
        lines.append("")

    log_content = "\n".join(lines)
    log_path.write_text(log_content, encoding="utf-8")
    logger.info("Chat log saved to %s", log_path)
    return log_path


def interactive_chat(
    session_markdown: str,
    llm_client: LLMClient,
    config: AppConfig,
    session_id: int,
) -> None:
    """Start an interactive chat about a saved session.

    Args:
        session_markdown: The session markdown content
        llm_client: Initialized LLM client
        config: Application configuration
        session_id: Session ID or filename for logging
    """
    # Get LLM context size
    health = llm_client.health_check()
    context_size = health.get("context_size") or 4096  # Default to 4K if unknown

    # Estimate tokens for session content (conservative: 1 token = 4 chars)
    session_tokens = len(session_markdown) // 4

    # Truncate if necessary (reserve ~1000 tokens for conversation)
    max_session_tokens = context_size - 1000
    if session_tokens > max_session_tokens:
        console.print(
            "[yellow]Session content is large, truncating for LLM context...[/yellow]"
        )
        session_markdown = _truncate_text_to_tokens(
            session_markdown, max_session_tokens
        )

    # Extract metadata for display
    metadata = _extract_frontmatter(session_markdown)
    language = metadata.get("language_code", "Unknown")
    level = metadata.get("level", "Unknown")
    score = metadata.get("overall_score", 0)

    # Display header
    console.print()
    console.print(
        Panel(
            f"[bold]Session Review Chat[/bold]\n"
            f"Language: {language} | Level: {level} | Score: {score:.1f}/100\n"
            f"\n"
            f"You can ask questions about this practice session. The LLM has access to the full session data.\n"
            f"Type 'quit' or 'exit' to end the chat.",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    # System prompt
    system_prompt = f"""You are a language tutor reviewing a previous practice session.

## Your Role
- Answer questions about the session content, vocabulary, translation, and comprehension questions
- Provide explanations and clarifications about language concepts
- Suggest improvements and additional practice based on the session results
- Be supportive and educational

## Session Data
Below is the complete session data in Markdown format. Use this information to answer questions.

{session_markdown}

## Instructions
1. Answer questions based on the session data above
2. If asked about something not in the session data, say you don't have that information
3. Keep responses concise but thorough
4. Use the vocabulary list and assessments to guide your explanations

Begin by greeting the user and offering to help review the session."""

    # Initialize conversation
    conversation: list[tuple[str, str]] = []

    # Initial LLM greeting
    console.print("[dim]Initializing chat...[/dim]")
    try:
        greeting = llm_client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Hello, let's review this session."},
            ],
            temperature=0.7,
        )
        console.print(f"[bold cyan]Tutor:[/bold cyan] {greeting}")
        conversation.append(("tutor", greeting))
    except Exception as e:
        console.print(f"[red]Failed to initialize chat: {e}[/red]")
        return

    # Chat loop
    while True:
        try:
            user_input = pt_prompt(HTML("<b>You: </b>"))
            user_input = user_input.strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[dim]Ending chat...[/dim]")
                break

            # Add user message to conversation
            conversation.append(("user", user_input))

            # Build message history for LLM (last 10 exchanges to manage context)
            messages = [{"role": "system", "content": system_prompt}]

            # Add recent conversation history
            for role, content in conversation[-10:]:  # Last 5 exchanges (10 messages)
                messages.append(
                    {
                        "role": "user" if role == "user" else "assistant",
                        "content": content,
                    }
                )

            # Get response
            with console.status("[bold yellow]Thinking..."):
                response = llm_client.chat_completion(
                    messages=messages,
                    temperature=0.7,
                )

            console.print(f"[bold cyan]Tutor:[/bold cyan] {response}")
            conversation.append(("tutor", response))

        except KeyboardInterrupt:
            console.print("\n[dim]Chat interrupted.[/dim]")
            break
        except EOFError:
            console.print("\n[dim]End of input.[/dim]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.exception("Chat error")
            break

    # Save chat log
    try:
        log_path = _save_chat_log(session_markdown, conversation, session_id)
        console.print(f"[dim]Chat log saved to {log_path}[/dim]")
    except Exception as e:
        logger.warning("Failed to save chat log: %s", e)
        console.print("[yellow]Failed to save chat log.[/yellow]")

    console.print("\n[bold cyan]Review session complete.[/bold cyan]")
