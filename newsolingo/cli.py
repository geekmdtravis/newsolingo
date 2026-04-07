"""Interactive CLI session orchestrator.

This is the main user-facing module that runs the full practice session:
language selection -> subject selection -> article fetch -> reading ->
translation -> assessment -> questions -> scoring -> progress check.
"""

from __future__ import annotations

import logging
import sys

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from newsolingo.config import AppConfig, load_config
from newsolingo.exercise.questions import generate_questions
from newsolingo.exercise.reading import prepare_reading_exercise
from newsolingo.fetcher.sources import load_sources, SourceRegistry
from newsolingo.languages.registry import get_language_info
from newsolingo.llm.assessor import assess_answer, assess_translation
from newsolingo.llm.client import LLMClient
from newsolingo.storage.database import Database
from newsolingo.storage.models import AdaptedArticle, SessionResult
from newsolingo.storage.progress import get_progress_report

logger = logging.getLogger(__name__)
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )
    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("trafilatura").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logger.debug("Logging configured with level %s", logging.getLevelName(level))


def _pick_option(prompt_text: str, options: list[str]) -> str:
    """Present a numbered list and let the user pick."""
    console.print()
    for i, opt in enumerate(options, 1):
        console.print(f"  [cyan]{i}[/cyan]. {opt}")
    console.print()

    while True:
        try:
            choice = pt_prompt(HTML(f"<b>{prompt_text}</b> "))
            choice = choice.strip()
            if not choice:
                continue
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]
            console.print(
                f"[red]Please enter a number between 1 and {len(options)}[/red]"
            )
        except (ValueError, EOFError):
            console.print(
                f"[red]Please enter a number between 1 and {len(options)}[/red]"
            )


def _ask_yes_no(prompt_text: str, default: bool = True) -> bool:
    """Ask a yes/no question with a default value."""
    default_text = "Y/n" if default else "y/N"
    while True:
        try:
            response = pt_prompt(HTML(f"<b>{prompt_text} ({default_text}): </b>"))
            response = response.strip().lower()
            if not response:
                return default
            if response in ("y", "yes"):
                return True
            if response in ("n", "no"):
                return False
            console.print("[red]Please enter 'y' or 'n'[/red]")
        except (EOFError, KeyboardInterrupt):
            return default


def _multiline_input(prompt_text: str) -> str:
    """Get multiline input from the user. Empty line to finish."""
    console.print(f"\n[bold]{prompt_text}[/bold]")
    console.print(
        "[dim](Type your response. Press Enter twice on an empty line to finish.)[/dim]"
    )

    lines: list[str] = []
    empty_count = 0

    while True:
        try:
            line = pt_prompt("> ")
            if line.strip() == "":
                empty_count += 1
                if empty_count >= 1 and lines:
                    break
                if not lines:
                    empty_count = 0
                    continue
            else:
                empty_count = 0
                lines.append(line)
        except EOFError:
            break

    return "\n".join(lines)


def _display_article(article: AdaptedArticle) -> None:
    """Display the adapted article with vocabulary panel."""
    # Article panel
    lang_info = get_language_info(article.language_code)
    direction_note = ""
    if lang_info and lang_info.direction == "rtl":
        direction_note = " [dim](RTL)[/dim]"

    console.print()
    console.print(
        Panel(
            article.adapted_text,
            title=f"Reading Exercise - {article.source_name}{direction_note}",
            subtitle=f"Level: {article.level} | Subject: {article.subject}",
            border_style="green",
            padding=(1, 2),
        )
    )

    # Vocabulary table
    if article.vocabulary:
        vocab_table = Table(
            title="Vocabulary",
            box=box.ROUNDED,
            border_style="blue",
            show_header=True,
            header_style="bold blue",
        )
        vocab_table.add_column("Term", style="bold")
        vocab_table.add_column("Translation", style="green")
        vocab_table.add_column("Context", style="dim")

        for v in article.vocabulary:
            vocab_table.add_row(v.term, v.translation, v.context)

        console.print()
        console.print(vocab_table)

    if article.original_url:
        console.print(f"\n[dim]Source: {article.original_url}[/dim]")


def _display_translation_result(assessment: object) -> None:
    """Display the translation assessment."""
    from newsolingo.storage.models import TranslationAssessment

    assert isinstance(assessment, TranslationAssessment)

    score_color = (
        "green"
        if assessment.score >= 70
        else "yellow"
        if assessment.score >= 50
        else "red"
    )

    console.print()
    console.print(
        Panel(
            f"[{score_color} bold]Score: {assessment.score:.0f}/100[/{score_color} bold]\n\n"
            f"[bold]Accuracy:[/bold] {assessment.accuracy}\n\n"
            f"[bold]Nuance:[/bold] {assessment.nuance}\n\n"
            f"[bold]Completeness:[/bold] {assessment.completeness}\n\n"
            f"[bold]Suggestions:[/bold] {assessment.suggestions}",
            title="Translation Assessment",
            border_style=score_color,
            padding=(1, 2),
        )
    )

    if assessment.corrected_translation:
        console.print(
            Panel(
                assessment.corrected_translation,
                title="Suggested Translation",
                border_style="blue",
                padding=(1, 2),
            )
        )


def _display_session_summary(result: SessionResult) -> None:
    """Display the final session summary."""
    score_color = (
        "green"
        if result.overall_score >= 70
        else "yellow"
        if result.overall_score >= 50
        else "red"
    )

    summary_table = Table(
        title="Session Summary",
        box=box.DOUBLE,
        border_style=score_color,
        show_header=True,
        header_style="bold",
    )
    summary_table.add_column("Component", style="bold")
    summary_table.add_column("Score", justify="center")

    summary_table.add_row(
        "Translation (40%)",
        f"{result.translation_score:.0f}/100",
    )
    summary_table.add_row(
        "Questions (60%)",
        f"{result.questions_score:.0f}/100",
    )
    summary_table.add_row(
        "[bold]Overall[/bold]",
        f"[{score_color} bold]{result.overall_score:.0f}/100[/{score_color} bold]",
    )

    console.print()
    console.print(summary_table)


def _display_progress(db: Database, config: AppConfig, language_code: str) -> None:
    """Display progress report and advancement suggestion if applicable."""
    report = get_progress_report(db, config, language_code)

    if report.total_sessions == 0:
        console.print("\n[dim]This is your first session! Keep practicing.[/dim]")
        return

    console.print()
    progress_table = Table(
        title=f"Progress - {report.language_name} ({report.current_level})",
        box=box.ROUNDED,
        border_style="cyan",
    )
    progress_table.add_column("Metric", style="bold")
    progress_table.add_column("Value", justify="center")

    progress_table.add_row("Total Sessions", str(report.total_sessions))
    if report.rolling_average is not None:
        progress_table.add_row(
            "Rolling Average (last 10)", f"{report.rolling_average:.1f}"
        )
    if report.all_time_average is not None:
        progress_table.add_row("All-Time Average", f"{report.all_time_average:.1f}")
    if report.best_score is not None:
        progress_table.add_row("Best Score", f"{report.best_score:.0f}")
    if report.avg_translation is not None:
        progress_table.add_row("Avg Translation Score", f"{report.avg_translation:.1f}")
    if report.avg_questions is not None:
        progress_table.add_row("Avg Questions Score", f"{report.avg_questions:.1f}")

    console.print(progress_table)

    if report.should_suggest_advancement and report.suggested_next_level:
        console.print()
        console.print(
            Panel(
                f"Your rolling average is [bold green]{report.rolling_average:.1f}[/bold green] "
                f"over your last {config.advancement.min_sessions} sessions.\n\n"
                f"Consider advancing from [bold]{report.current_level}[/bold] "
                f"to [bold green]{report.suggested_next_level}[/bold green]!\n\n"
                f"Update your level in your configuration file when you're ready.",
                title="Level Advancement Suggestion",
                border_style="green",
                padding=(1, 2),
            )
        )


def run_session(
    config: AppConfig,
    llm_client: LLMClient,
    db: Database,
    source_registry: SourceRegistry,
    url: str | None = None,
    language: str | None = None,
    subject: str | None = None,
) -> None:
    """Run a single interactive practice session."""
    # Direct URL mode
    if url is not None:
        if language is None:
            console.print("[red]Internal error: URL provided without language[/red]")
            return
        lang_code = language
        lang_config = config.get_language(lang_code)
        subject = subject or "Direct"
        # Skip welcome panel? Keep it brief.
        console.print(
            Panel(
                f"[bold]Direct URL Mode[/bold]\nScraping article from {url}",
                border_style="cyan",
            )
        )
        console.print(
            f"\n[bold]Language:[/bold] {lang_config.name} | [bold]Level:[/bold] {lang_config.level}"
        )
        # Ask about accents/transliteration
        lang_info = get_language_info(lang_code)
        if lang_info and lang_info.script == "latin":
            prompt_text = "Ignore missing accents in your answers? (e.g., á vs a)"
        else:
            prompt_text = "Accept transliteration in your answers? (e.g., Latin letters instead of original script)"
        ignore_accents = _ask_yes_no(prompt_text, default=True)
        # Fetch and adapt article from URL
        console.print("\n[yellow]Fetching and adapting article...[/yellow]")
        with console.status("[bold yellow]Scraping URL..."):
            article = prepare_reading_exercise(
                config=config,
                llm_client=llm_client,
                db=db,
                source_registry=source_registry,
                language_code=lang_code,
                subject=subject,
                direct_url=url,
            )
    else:
        # Interactive mode (original flow)
        console.print(
            Panel(
                "[bold]Welcome to Newsolingo![/bold]\n"
                "Practice your language skills with real-world content.",
                border_style="cyan",
            )
        )
        # Step 1: Language selection
        available_languages = list(config.languages.keys())
        if not available_languages:
            console.print(
                "[red]No languages configured. Add languages to your configuration file.[/red]"
            )
            return

        if len(available_languages) == 1:
            lang_code = available_languages[0]
            lang_config = config.get_language(lang_code)
            console.print(
                f"Language: [bold]{lang_config.name}[/bold] (Level: {lang_config.level})"
            )
        else:
            lang_labels = []
            for code in available_languages:
                lc = config.get_language(code)
                lang_labels.append(f"{lc.name} (Level: {lc.level})")

            chosen_label = _pick_option("Select language:", lang_labels)
            lang_code = available_languages[lang_labels.index(chosen_label)]
            lang_config = config.get_language(lang_code)

        console.print(
            f"\n[bold]Language:[/bold] {lang_config.name} | [bold]Level:[/bold] {lang_config.level}"
        )

        # Step 2: Subject selection
        available_subjects = source_registry.get_subjects(lang_code)
        configured_subjects = [
            s for s in lang_config.subjects if s in available_subjects
        ]

        if not configured_subjects:
            # Fall back to all available subjects
            configured_subjects = available_subjects

        if not configured_subjects:
            console.print(
                f"[red]No content sources available for {lang_config.name}.[/red]"
            )
            return

        subject_options = ["Random"] + configured_subjects
        chosen_subject = _pick_option("Select subject:", subject_options)
        subject = None if chosen_subject == "Random" else chosen_subject

        # Ask about accents/transliteration
        lang_info = get_language_info(lang_code)
        if lang_info and lang_info.script == "latin":
            prompt_text = "Ignore missing accents in your answers? (e.g., á vs a)"
        else:
            prompt_text = "Accept transliteration in your answers? (e.g., Latin letters instead of original script)"
        ignore_accents = _ask_yes_no(prompt_text, default=True)

        # Step 3: Fetch and adapt article
        console.print("\n[yellow]Fetching and adapting article...[/yellow]")
        with console.status("[bold yellow]Crawling for articles..."):
            article = prepare_reading_exercise(
                config=config,
                llm_client=llm_client,
                db=db,
                source_registry=source_registry,
                language_code=lang_code,
                subject=subject,
            )

    if not article:
        console.print(
            "[red]Could not fetch any article. Try again later or check your sources.[/red]"
        )
        return

    # Create the session in the database
    session_id = db.create_session(
        language_code=lang_code,
        article_id=article.article_id or 0,
        level=lang_config.level,
        ignore_accents=ignore_accents,
    )

    # Step 4: Display reading exercise
    _display_article(article)

    console.print("\n[bold cyan]Take your time to read the text above.[/bold cyan]")
    console.print("[dim]When you're ready, translate it to English below.[/dim]")

    # Step 5: Get user's translation
    user_translation = _multiline_input("Your English translation:")

    if not user_translation.strip():
        console.print(
            "[yellow]No translation provided. Skipping translation assessment.[/yellow]"
        )
        translation_assessment = None
    else:
        # Step 6: Assess translation
        console.print("\n[yellow]Assessing your translation...[/yellow]")
        with console.status("[bold yellow]LLM is grading..."):
            translation_assessment = assess_translation(
                client=llm_client,
                adapted_text=article.adapted_text,
                user_translation=user_translation,
                language_code=lang_code,
                level=lang_config.level,
                ignore_accents=ignore_accents,
            )
        _display_translation_result(translation_assessment)

    # Step 7: Generate comprehension questions
    console.print("\n[yellow]Generating comprehension questions...[/yellow]")
    with console.status("[bold yellow]Creating questions..."):
        questions = generate_questions(
            client=llm_client,
            adapted_text=article.adapted_text,
            language_code=lang_code,
            level=lang_config.level,
            num_questions=config.exercise.num_questions,
        )

    # Step 8: Ask questions and get answers
    console.print(
        Panel(
            f"[bold]Answer the following {len(questions)} questions in {lang_config.name}.[/bold]\n"
            "[dim]Try to use the vocabulary from the text.[/dim]",
            border_style="cyan",
        )
    )

    user_answers: list[str] = []
    answer_assessments = []

    for i, q in enumerate(questions, 1):
        console.print(f"\n[bold cyan]Question {i}/{len(questions)}:[/bold cyan]")
        console.print(f"  {q.question}")

        answer = pt_prompt(HTML(f"<b>Your answer: </b>"))
        user_answers.append(answer.strip())

        if not answer.strip():
            console.print("[dim]Skipped.[/dim]")
            from newsolingo.storage.models import AnswerAssessment

            answer_assessments.append(
                AnswerAssessment(
                    score=0,
                    correctness="No answer provided",
                    grammar="N/A",
                    feedback="Try to answer next time!",
                )
            )
            continue

        # Assess each answer
        with console.status("[bold yellow]Grading..."):
            assessment = assess_answer(
                client=llm_client,
                adapted_text=article.adapted_text,
                question=q.question,
                user_answer=answer,
                expected_hint=q.expected_answer_hint,
                language_code=lang_code,
                level=lang_config.level,
                ignore_accents=ignore_accents,
            )
        answer_assessments.append(assessment)

        # Show immediate feedback
        score_color = (
            "green"
            if assessment.score >= 70
            else "yellow"
            if assessment.score >= 50
            else "red"
        )
        console.print(
            f"  [{score_color}]Score: {assessment.score:.0f}/100[/{score_color}]"
        )
        console.print(f"  [dim]{assessment.feedback}[/dim]")

        # Save to database
        db.save_question_response(
            session_id=session_id,
            question_text=q.question,
            user_answer=answer,
            score=assessment.score,
            feedback=assessment.feedback,
        )

    # Step 9: Compute and save scores
    from newsolingo.storage.models import TranslationAssessment as TA

    if translation_assessment is None:
        translation_assessment = TA(
            score=0,
            accuracy="Not attempted",
            nuance="N/A",
            completeness="N/A",
            suggestions="Try translating next time!",
        )

    session_result = SessionResult(
        session_id=session_id,
        language_code=lang_code,
        level=lang_config.level,
        ignore_accents=ignore_accents,
        article=article,
        user_translation=user_translation or "",
        translation_assessment=translation_assessment,
        questions=questions,
        user_answers=user_answers,
        answer_assessments=answer_assessments,
    )

    # Save final scores
    db.update_session_scores(
        session_id=session_id,
        translation_score=session_result.translation_score,
        questions_score=session_result.questions_score,
        overall_score=session_result.overall_score,
        feedback={
            "translation": {
                "score": translation_assessment.score,
                "accuracy": translation_assessment.accuracy,
                "suggestions": translation_assessment.suggestions,
            },
            "questions": [
                {"score": a.score, "feedback": a.feedback} for a in answer_assessments
            ],
        },
    )

    # Step 10: Display summary
    _display_session_summary(session_result)

    # Step 11: Show progress
    _display_progress(db, config, lang_code)


def run(
    verbose: bool = False,
    url: str | None = None,
    language: str | None = None,
    subject: str | None = None,
) -> None:
    """Main entry point - initialize everything and run the session loop.

    If url and language are provided, runs a single session with that URL.
    """
    _setup_logging(verbose)

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]Failed to load configuration: {e}[/red]")
        sys.exit(1)

    # Validate URL/language parameters
    if url is not None:
        if language is None:
            console.print("[red]Error: --url requires --language to be specified[/red]")
            sys.exit(1)
        if language not in config.languages:
            console.print(
                f"[red]Error: Language '{language}' not found in configuration[/red]"
            )
            sys.exit(1)
        subject = subject or "Direct"
    else:
        # If URL not provided, language must be selected interactively
        language = None
        subject = None

    console.print(f"[dim]Hello, {config.user.name}! Loading Newsolingo...[/dim]")

    # Initialize components
    try:
        llm_client = LLMClient(config)
    except Exception as e:
        console.print(f"[red]Failed to initialize LLM client: {e}[/red]")
        sys.exit(1)

    # Verify LLM server is reachable before proceeding
    health = llm_client.health_check()
    if not health["ok"]:
        provider = health["provider"]
        console.print(f"\n[red bold]LLM server is not reachable.[/red bold]")
        console.print(f"[red]{health['error']}[/red]\n")
        if provider == "llamacpp":
            url = config.llm.llamacpp.base_url.rstrip("/v1").rstrip("/")
            console.print("[yellow]To fix this, start your llama.cpp server:[/yellow]")
            console.print(
                f"  llama-server -m <model.gguf> --port {url.split(':')[-1]}\n"
            )
            console.print(
                "[yellow]Or switch to OpenRouter in your configuration file:[/yellow]"
            )
            console.print("  llm:")
            console.print('    provider: "openrouter"')
        elif provider == "openrouter":
            console.print(
                "[yellow]Check your OPENROUTER_API_KEY and network connection.[/yellow]"
            )
        elif provider == "deepseek":
            console.print(
                "[yellow]Check your DEEPSEEK_API_KEY and network connection.[/yellow]"
            )
        sys.exit(1)
    else:
        ctx_info = ""
        if health.get("context_size"):
            ctx_info = f", context: {health['context_size']} tokens"
        console.print(
            f"[dim]LLM: {health['provider']} ({health['model']}{ctx_info})[/dim]"
        )

    db = Database()
    db.initialize()

    # Sync language levels from config to database
    for code, lang in config.languages.items():
        db.upsert_language(code, lang.name, lang.level)

    source_registry = load_sources()

    # Run session loop
    single_session = url is not None
    while True:
        try:
            run_session(
                config,
                llm_client,
                db,
                source_registry,
                url=url,
                language=language,
                subject=subject,
            )
        except KeyboardInterrupt:
            console.print("\n[dim]Session interrupted.[/dim]")
        except Exception as e:
            logger.exception("Session error")
            console.print(f"\n[red]Error during session: {e}[/red]")

        if single_session:
            break

        console.print()
        try:
            again = pt_prompt(HTML("<b>Start another session? (y/n): </b>"))
            if again.strip().lower() not in ("y", "yes"):
                break
        except (EOFError, KeyboardInterrupt):
            break

    db.close()
    console.print("\n[bold cyan]Thanks for practicing! See you next time.[/bold cyan]")
