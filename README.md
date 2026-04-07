# Newsolingo

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/) [![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-black)](https://github.com/astral-sh/ruff)

A language learning CLI that fetches real-world articles and creates CEFR-adapted reading exercises.

> **Note:** This project is in active development. Feedback and contributions welcome!

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Supported Languages and Sources](#supported-languages-and-sources)
- [How It Works](#how-it-works)
- [Development](#development)
- [Testing](#testing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Overview

Newsolingo helps you practice a foreign language by fetching articles from authentic websites (news, blogs, etc.), adapting them to your CEFR level (pre‑A1 through C2), and generating interactive exercises. You read the adapted text, translate it to English, answer comprehension questions, and receive AI‑powered feedback with detailed scoring.

The system tracks your progress across sessions, suggests when you’re ready to advance to the next CEFR level, and stores everything in a local SQLite database.

## Features

* **Real‑world content** – Articles scraped from live websites in the target language (Linux, programming, geopolitics, exercise science, biblical Hebrew, etc.).
* **CEFR‑level adaptation** – Uses an LLM (DeepSeek, OpenRouter, or a local llama.cpp server) to rewrite articles at your current proficiency.
* **Vocabulary panel** – Highlights key terms with translations and contextual examples.
* **Translation exercise** – Submit your English translation and get an AI‑assessed score with accuracy, nuance, and completeness breakdowns.
* **Comprehension questions** – Answer 4 (configurable) questions in the target language; each answer is graded for correctness and grammar.
* **Progress tracking** – Rolling‑average scores, best‑session highlights, and automatic advancement suggestions.
* **Multiple LLM providers** – Works with DeepSeek (free tier), OpenRouter, or any OpenAI‑compatible local server (llama.cpp).
* **Rich CLI interface** – Built with `rich` and `prompt‑toolkit` for a pleasant, color‑rich terminal experience.
* **Direct‑URL mode** – Provide a specific article URL and language to practice with any content you choose.
* **XDG‑based configuration** – Configuration lives in `~/.config/newsolingo/config.yaml`; environment‑variable substitution supported.

## Installation

### From source (recommended)

1. Clone the repository:

   ```bash
   git clone https://github.com/geekmdtravis/newsolingo.git
   cd newsolingo
   ```

2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

   Or, if you use `uv`:

   ```bash
   uv venv
   uv sync
   source .venv/bin/activate
   ```

### From PyPI (future)

```bash
pip install newsolingo
```

## Configuration

Newsolingo expects a configuration file at `~/.config/newsolingo/config.yaml`. On first run, a template will be created there automatically.

You can also copy the example file `config.yaml.example` to that location and edit it.

### Minimal example

```yaml
user:
  name: "Your Name"

languages:
  pt_br:
    name: "Brazilian Portuguese"
    level: "A2"
    subjects:
      - linux
      - programming
      - geopolitics
  he:
    name: "Hebrew"
    level: "pre-A1"
    subjects:
      - biblical_hebrew

llm:
  provider: "deepseek"
  deepseek:
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"

advancement:
  threshold_score: 80
  min_sessions: 10

exercise:
  num_questions: 4
  max_adapted_length: 2000
```

### LLM providers

| Provider   | Required setting                     | Notes                                                                 |
|------------|--------------------------------------|-----------------------------------------------------------------------|
| `deepseek` | `api_key` (or `DEEPSEEK_API_KEY` env) | Free tier available; set model to `deepseek-chat` (default).          |
| `openrouter` | `api_key` (or `OPENROUTER_API_KEY` env) | Many models; default is `minimax/minimax-m2.5:free`.                  |
| `llamacpp` | `base_url` (e.g., `http://127.0.0.1:8089/v1`) | Run a local llama.cpp server; `model` field is ignored but required.  |

### Adding a language

Use the interactive wizard:

```bash
newsolingo config add-language
```

Or edit `config.yaml` manually:

```yaml
languages:
  es:
    name: "Spanish"
    level: "B1"
    subjects:
      - geopolitics
      - programming
```

## Usage

### Interactive session (default)

```bash
newsolingo run
```

You will be guided through:
1. Language selection (if more than one configured)
2. Subject selection (Random, Linux, Programming, Geopolitics, Exercise Science, Biblical Hebrew)
3. Article fetching and adaptation
4. Reading exercise with vocabulary panel
5. Translation to English (graded)
6. Comprehension questions (graded)
7. Session summary and progress report

### Direct URL mode

Practice with a specific article:

```bash
newsolingo run --url "https://example.com/article" --language pt_br
```

The article will be scraped and adapted to the level configured for that language.

### Configuration management

```bash
# Show current configuration
newsolingo config show

# Set a configuration value (dot notation)
newsolingo config set llm.provider deepseek

# Edit config file with $EDITOR
newsolingo config edit

# Interactive language‑addition wizard
newsolingo config add-language
```

### Reset database

```bash
newsolingo run --reset-db
```

Deletes all session history and article cache. You will be prompted for confirmation.

## Supported Languages and Sources

Currently included source definitions:

* **Brazilian Portuguese (`pt_br`)**
  * Linux (`diolinux.com.br`, `vivaolinux.com.br`, `linuxdescomplicado.com.br`)
  * Programming (`tabnews.com.br`, `alura.com.br/artigos`, `dev.to/t/portuguese`)
  * Geopolitics (`bbc.com/portuguese`, `g1.globo.com/mundo`, `cartacapital.com.br/mundo`)
  * Exercise Science (`uol.com.br/vivabem`, `ge.globo.com/eu-atleta`)
  * Biblical Hebrew (`estudosdabiblia.net`)

* **Hebrew (`he`)**
  * Biblical Hebrew (`balashon.com`, `safa-ivrit.org`)
  * (Other subjects are intentionally empty because many Israeli sites block scraping.)

You can add your own source YAML files in the `sources/` directory. Each file is named after the language code (e.g., `es.yaml`) and follows this structure:

```yaml
subjects:
  linux:
    - url: "https://example.com"
      name: "Example Site"
      type: "blog"
      description: "A short description"
```

## How It Works

1. **Content fetching** – Using `trafilatura` and `httpx`, the system scrapes the HTML of a randomly chosen source URL for the selected language/subject.
2. **CEFR adaptation** – The raw article text is sent to the configured LLM with a prompt that asks to rewrite it at the learner’s CEFR level, simplify vocabulary, and add glosses for key terms.
3. **Exercise generation** – The adapted text is used to generate a vocabulary panel (term, translation, context) and a set of comprehension questions (with expected‑answer hints).
4. **Interactive session** – The learner reads the text, translates it, and answers questions. Each submission is assessed by the LLM with rubrics for translation (accuracy, nuance, completeness) and answers (correctness, grammar).
5. **Scoring & progress** – Translation (40%) and questions (60%) are combined into an overall score. The rolling average of the last 10 sessions is compared against the advancement threshold; if exceeded, the next CEFR level is suggested.
6. **Persistence** – All sessions, articles, and scores are stored in a local SQLite database (`~/.local/share/newsolingo/newsolingo.db` by default).

## Development

### Project structure

```
newsolingo/
├── newsolingo/
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point (argument parsing)
│   ├── cli.py               # Interactive session orchestration
│   ├── config.py            # Pydantic configuration models
│   ├── config_cli.py        # Configuration subcommands
│   ├── storage/             # Database models, progress tracking
│   ├── fetcher/             # Web scraping, source registry
│   ├── exercise/            # Reading adaptation, question generation
│   ├── llm/                 # LLM client, prompts, assessment
│   └── languages/           # Language metadata (script, direction, etc.)
├── sources/                 # YAML files defining content sources per language
├── tests/                   # Unit tests
├── test_integration.py      # Integration test
├── config.yaml.example      # Example configuration
├── pyproject.toml           # Project metadata and dependencies
└── README.md                # This file
```

### Running tests

```bash
# Unit tests
pytest tests/

# Integration test (requires a configured LLM)
python test_integration.py
```

### Code style

The project uses `ruff` for linting and formatting:

```bash
ruff check .
ruff format .
```

### Adding a new language source

1. Create `sources/<language_code>.yaml` with the structure shown above.
2. Add the language to your `config.yaml`.
3. The next interactive session will include the new subject(s).

### Adding a new LLM provider

Extend `newsolingo/llm/client.py` and `newsolingo/config.py` to support additional OpenAI‑compatible endpoints.

## Testing

Unit tests are located in `tests/`. Integration tests require a working LLM provider and can be run with `python test_integration.py`. The test suite verifies:

* Configuration loading and validation
* Source registry loading
* Database operations
* LLM health checks
* Exercise generation (with mocked LLM responses)

## License

[MIT](LICENSE) – see the `LICENSE` file.

## Acknowledgments

* Built with [`trafilatura`](https://trafilatura.readthedocs.io/) for reliable web‑text extraction.
* Uses [`rich`](https://github.com/Textualize/rich) for beautiful terminal output.
* LLM integration via the OpenAI‑compatible API.
* CEFR level definitions based on the Common European Framework of Reference for Languages.