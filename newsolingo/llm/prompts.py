"""Prompt templates for LLM interactions.

All prompts are centralized here for easy editing and tuning.
"""

from newsolingo.languages.registry import get_language_info

# CEFR level descriptions to help the LLM understand what each level means
CEFR_DESCRIPTIONS = {
    "pre-A1a": (
        "Absolute beginner. Use only the most basic words (10-20 word vocabulary). "
        "Choose words from what be among the most common."
        "Write 1-2 very short sentences maximum. Use only present tense. "
        "Use only subject-verb-object structure. No complex grammar at all. "
        "Include transliterations for non-Latin scripts and nikkud on Hebrew letters."
        "The goal is to build a very basic vocabulary foundation and simple sentence structure only."
        "Choose what should be the top 20 most useful beginner words in the language as the core of the exercises."
    ),
    "pre-A1b": (
        "Absolute beginner. Use only the most basic words (20-50 word vocabulary). "
        "Choose words from what be among the most common."
        "Write 2-3 very short sentences maximum. Use only present tense. "
        "Use only subject-verb-object structure. No complex grammar at all. "
        "Include transliterations for non-Latin scripts and nikkud on Hebrew letters."
        "The goal is to add to the very basic vocabulary foundation and simple sentence structure only."
        "Choose what should be the top 50 most useful beginner words in the language as the core of the exercises."
    ),
    "A1": (
        "Beginner. Use basic everyday vocabulary (up to ~500 words). "
        "Write short, simple sentences. Use present tense mainly. "
        "Topics: self, family, immediate environment. Simple descriptions only."
    ),
    "A2": (
        "Elementary. Use common everyday expressions and basic phrases. "
        "Short paragraphs are okay. Simple past and future tenses allowed. "
        "Can describe background, immediate environment, routine matters."
    ),
    "B1": (
        "Intermediate. Use standard vocabulary for familiar topics. "
        "Multiple paragraphs are fine. Use a range of tenses. "
        "Can express opinions, describe experiences, give reasons. "
        "Connected text on topics of personal interest."
    ),
    "B2": (
        "Upper intermediate. Use a broad vocabulary including some specialized terms. "
        "Complex sentence structures allowed. Use subjunctive, conditionals, passive voice. "
        "Can present clear, detailed text on a wide range of subjects."
    ),
    "C1": (
        "Advanced. Use rich, sophisticated vocabulary including idiomatic expressions. "
        "Complex grammatical structures freely. Nuanced expression. "
        "Can produce clear, well-structured, detailed text on complex subjects."
    ),
    "C2": (
        "Mastery. Native-like proficiency. Use the full range of the language. "
        "Colloquialisms, subtle nuances, literary references all acceptable. "
        "Near-native text that reads naturally."
    ),
}

LANGUAGE_NAMES = {
    "pt_br": "Brazilian Portuguese",
    "he": "Hebrew",
}


def adapt_article_system_prompt(language_code: str, level: str) -> str:
    """System prompt for adapting an article to a CEFR level."""
    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    level_desc = CEFR_DESCRIPTIONS.get(level, "Intermediate level")

    return f"""You adapt {lang_name} articles for CEFR {level} learners.

{level}: {level_desc}

Rules:
1. Keep text in {lang_name}. Do NOT translate to English.
2. Simplify vocabulary and grammar to match {level}.
3. Preserve the core meaning of the article.
4. Adapted text MUST be short: 1-2 sentences for pre-A1, 3-5 sentences for A1, 1-2 short paragraphs for A2/B1, 2-3 paragraphs for B2+.
5. Vocabulary list: exactly 5-8 key terms maximum.
6. For Hebrew pre-A1a/pre-A1b/A1: add nikkud (vowel marks).

Respond ONLY with compact JSON (no extra whitespace):
{{"adapted_text":"...","vocabulary":[{{"term":"...","translation":"...","context":"..."}}]}}"""


def adapt_article_user_prompt(original_text: str, max_length: int = 2000) -> str:
    """User prompt for article adaptation."""
    # Truncate articles aggressively to leave room for the response in limited context
    if len(original_text) > 2000:
        original_text = original_text[:2000] + "\n[truncated]"

    return f"""Adapt this article. Keep adapted_text under {max_length} chars. Output valid JSON only.

{original_text}"""


def assess_translation_system_prompt(
    language_code: str, level: str, ignore_accents: bool = True
) -> str:
    """System prompt for assessing a translation."""
    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    lang_info = get_language_info(language_code)

    accent_instruction = ""
    if ignore_accents and lang_info:
        if lang_info.script == "latin":
            accent_instruction = "\n\n**Important**: The student may omit accents (e.g., write 'a' instead of 'á'). This is acceptable - do not penalize for missing accents."
        elif lang_info.script == "hebrew":
            accent_instruction = "\n\n**Important**: The student may use transliteration (Latin letters) instead of Hebrew script. This is acceptable - do not penalize for using transliteration."

    return f"""You are an expert language teacher assessing a student's translation from {lang_name} to English.

The student is at CEFR level {level} in {lang_name}. Assess their translation considering their level.

Evaluate these dimensions:
1. **Accuracy**: Did they correctly translate the meaning?
2. **Nuance**: Did they capture subtleties, tone, and implied meanings?
3. **Completeness**: Did they translate all the important content?{accent_instruction}

Be encouraging but honest. Note specific mistakes and explain what the correct interpretation would be.
Adjust your expectations to the student's level - a B1 student won't catch every nuance, and that's okay.

You MUST respond in valid JSON with this exact structure:
{{
    "score": <number 0-100>,
    "accuracy": "Assessment of accuracy",
    "nuance": "Assessment of nuance capture",
    "completeness": "Assessment of completeness",
    "suggestions": "Specific suggestions for improvement",
    "corrected_translation": "Your suggested English translation of the text"
}}"""


def assess_translation_user_prompt(adapted_text: str, user_translation: str) -> str:
    """User prompt for translation assessment."""
    return f"""ORIGINAL TEXT (in the target language):
{adapted_text}

STUDENT'S ENGLISH TRANSLATION:
{user_translation}

Please assess the quality of this translation."""


def generate_questions_system_prompt(language_code: str, level: str) -> str:
    """System prompt for generating comprehension questions."""
    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    level_desc = CEFR_DESCRIPTIONS.get(level, "Intermediate level")

    return f"""You are a language teacher creating comprehension questions in {lang_name} for a student at CEFR level {level}.

Level description for {level}:
{level_desc}

Rules:
1. Write ALL questions in {lang_name} at the appropriate level.
2. Questions should test understanding of the article's content.
3. Mix question types: factual recall, inference, opinion/reaction.
4. The student will answer in {lang_name}, so make questions that encourage writing practice.
5. For pre-A1a and pre-A1b: use very simple yes/no or one-word-answer questions; emphasis on vocabulary building.
6. For A1: use very simple yes/no or one-word-answer questions.
7. For A2: use simple questions that may require short phrases or sentences.
8. For B1+: use open-ended questions requiring sentences.
9. For Hebrew at pre-A1a/pre-A1b: include transliteration of the questions.

You MUST respond in valid JSON with this exact structure:
{{
    "questions": [
        {{"question": "The question in {lang_name}", "expected_answer_hint": "Brief hint about what a good answer includes (in English)"}},
        ...
    ]
}}"""


def generate_questions_user_prompt(adapted_text: str, num_questions: int) -> str:
    """User prompt for question generation."""
    return f"""Based on the following text, generate {num_questions} comprehension questions.

TEXT:
{adapted_text}

Generate exactly {num_questions} questions. Remember to write them in the target language at the appropriate level."""


def assess_answer_system_prompt(
    language_code: str, level: str, ignore_accents: bool = True
) -> str:
    """System prompt for assessing a student's answer to a comprehension question."""
    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    lang_info = get_language_info(language_code)

    accent_instruction = ""
    if ignore_accents and lang_info:
        if lang_info.script == "latin":
            accent_instruction = "\n\n**Important**: The student may omit accents (e.g., write 'a' instead of 'á'). This is acceptable - do not penalize for missing accents."
        elif lang_info.script == "hebrew":
            accent_instruction = "\n\n**Important**: The student may use transliteration (Latin letters) instead of Hebrew script. This is acceptable - do not penalize for using transliteration."

    return f"""You are a {lang_name} language teacher assessing a student's answer to a comprehension question.
The student is at CEFR level {level}.

Evaluate:
1. **Correctness**: Is the answer factually correct based on the text?
2. **Grammar**: Is the {lang_name} grammar appropriate for their level?
3. **Vocabulary**: Are they using appropriate vocabulary?{accent_instruction}

Be encouraging but honest. Provide specific corrections where needed.
Grade on a scale of 0-100, considering their level.

You MUST respond in valid JSON with this exact structure:
{{
    "score": <number 0-100>,
    "correctness": "Assessment of content correctness",
    "grammar": "Assessment of grammar",
    "feedback": "Overall feedback with specific suggestions"
}}"""


def assess_answer_user_prompt(
    adapted_text: str,
    question: str,
    user_answer: str,
    expected_hint: str,
) -> str:
    """User prompt for answer assessment."""
    return f"""ARTICLE TEXT:
{adapted_text}

QUESTION:
{question}

EXPECTED ANSWER SHOULD INCLUDE:
{expected_hint}

STUDENT'S ANSWER:
{user_answer}

Please assess this answer."""
