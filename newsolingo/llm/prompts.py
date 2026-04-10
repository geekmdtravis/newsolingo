"""Prompt templates for LLM interactions.

All prompts are centralized here for easy editing and tuning.
"""

from newsolingo.languages.registry import get_language_info

# CEFR level descriptions to help the LLM understand what each level means
CEFR_DESCRIPTIONS = {
    "pre-A1a": (
        "Absolute beginner. Use only the most essential beginner words, roughly from a core vocabulary of about 10-20 words. "
        "Write only 1-2 very short sentences. Use present tense only. "
        "Use only simple subject-verb-object patterns and the most basic statements. "
        "Avoid subordinate clauses, idioms, abstract language, and complex grammar. "
        "The goal is recognition and repetition of the most useful beginner words only."
    ),
    "pre-A1b": (
        "Absolute beginner. Use only the most essential beginner words, roughly from a core vocabulary of about 20-50 words. "
        "Write only 2-3 very short sentences. Use present tense only. "
        "Use only very simple sentence patterns. "
        "Avoid subordinate clauses, idioms, abstract language, and complex grammar. "
        "The goal is to expand the earliest beginner vocabulary while keeping grammar extremely simple."
    ),
    "A1": (
        "Beginner. Use very common everyday vocabulary, roughly within the first 300-500 words a learner is likely to know. "
        "Write short and simple sentences. Use mainly present tense, with only very basic past or future if truly necessary. "
        "Focus on concrete topics such as people, places, daily routine, food, family, and basic actions. "
        "Avoid idioms, dense clauses, and advanced connectors."
    ),
    "A2": (
        "Elementary. Use common everyday expressions and high-frequency vocabulary. "
        "Short paragraphs are acceptable. Use simple present, past, and future where helpful. "
        "The learner can handle routine matters, simple descriptions, and basic explanations. "
        "Keep syntax straightforward and avoid unnecessary complexity."
    ),
    "B1": (
        "Intermediate. Use standard vocabulary for familiar topics and clear connected prose. "
        "Multiple short paragraphs are acceptable. Use a normal range of tenses. "
        "The learner can understand main points, describe experiences, express opinions, and give simple reasons. "
        "Use natural but not highly specialized language."
    ),
    "B2": (
        "Upper intermediate. Use a broad vocabulary, including some lower-frequency and topic-specific terms when needed. "
        "Complex sentence structures are acceptable, but remain readable. "
        "The learner can follow clear, detailed text and more nuanced explanations. "
        "Use natural connectors, some abstraction, and moderate stylistic variety."
    ),
    "C1": (
        "Advanced. Use rich, precise vocabulary and natural idiomatic phrasing where appropriate. "
        "Use complex grammatical structures freely. "
        "The learner can handle nuance, implied meaning, and detailed argumentation. "
        "Write natural, fluent text with clear structure."
    ),
    "C2": (
        "Mastery. Use the full natural range of the language. "
        "Colloquialisms, subtle shades of meaning, stylistic variation, and culturally natural phrasing are acceptable. "
        "Write as an educated native speaker might, while remaining clear and coherent."
    ),
}

LANGUAGE_NAMES = {
    "pt_br": "Brazilian Portuguese",
}


def _length_guidance(level: str) -> str:
    if level in {"pre-A1a", "pre-A1b"}:
        return "Keep the adapted text extremely short: 1-3 very short sentences."
    if level == "A1":
        return "Keep the adapted text short: about 3-5 short sentences."
    if level in {"A2", "B1"}:
        return "Keep the adapted text concise: about 1-2 short paragraphs."
    return "Keep the adapted text concise but complete: about 2-3 short paragraphs."


def _vocab_guidance(level: str) -> str:
    if level == "pre-A1a":
        return (
            "Prefer only the most useful beginner words. Stay close to a tiny core vocabulary. "
            "If the source is too hard, rewrite aggressively rather than preserving difficult wording."
        )
    if level == "pre-A1b":
        return (
            "Prefer only very common beginner words. Stay close to an early learner vocabulary. "
            "If the source is too hard, rewrite aggressively rather than preserving difficult wording."
        )
    if level == "A1":
        return "Prefer very common words over precise but rare words."
    if level == "A2":
        return "Prefer common words and short clauses; introduce only light variation."
    if level == "B1":
        return "Use mostly common words with some natural variety."
    if level == "B2":
        return (
            "Use a broad vocabulary, but avoid being unnecessarily literary or obscure."
        )
    if level == "C1":
        return "Use precise and natural vocabulary, including some idiomatic phrasing where helpful."
    return "Use fully natural vocabulary and style appropriate for an educated native speaker."


def adapt_article_system_prompt(language_code: str, level: str) -> str:
    """System prompt for adapting an article to a CEFR level."""
    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    level_desc = CEFR_DESCRIPTIONS.get(level, "Intermediate level")
    lang_info = get_language_info(language_code)

    script_instruction = ""
    if lang_info and lang_info.script != "latin":
        script_instruction = f"7. Keep the main text in {lang_name} script. Also provide transliteration in the vocabulary entries when useful.\n"

    return f"""You adapt source material into learner-friendly {lang_name} for a CEFR {level} student.

Level target:
{level}: {level_desc}

Your job:
- Rewrite the text so it is genuinely readable for this level.
- Preserve the core meaning and the most important facts.
- Remove or simplify details that are too difficult for this level.
- Do NOT translate into English.
- Do NOT explain your choices.
- Do NOT add information that was not in the source.

Difficulty guidance:
- {_length_guidance(level)}
- {_vocab_guidance(level)}

Rules:
1. Output only in {lang_name}.
2. Match the grammar, vocabulary, and sentence complexity to CEFR {level}.
3. Preserve the main idea and key facts, but simplify aggressively when needed.
4. Prefer short, clear sentences over fidelity to the original wording.
5. Vocabulary list must contain exactly 5-8 useful terms from the adapted text.
6. Each vocabulary item must be genuinely useful for a learner at this level.
{script_instruction}Return valid compact JSON only, with this exact schema:
{{"adapted_text":"...","vocabulary":[{{"term":"...","translation":"...","context":"..."}}]}}

Requirements for the JSON:
- No markdown
- No code fences
- No commentary
- No extra keys
- The JSON must parse exactly
"""


def adapt_article_user_prompt(original_text: str, max_length: int = 2000) -> str:
    """User prompt for article adaptation."""
    if len(original_text) > 2000:
        original_text = original_text[:2000] + "\n[truncated]"

    return f"""Rewrite the following source text for the target learner level.

Constraints:
- Keep adapted_text under {max_length} characters.
- Preserve the main meaning and the key facts.
- Make the text feel natural for the learner level, not merely shortened.
- Return valid JSON only.

SOURCE TEXT:
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
            accent_instruction = "\nAccent policy: Missing accents alone should not reduce the score unless they create confusion."

    return f"""You are an expert language teacher assessing a student's translation from {lang_name} into English.

The student is at CEFR level {level}. Judge the translation according to that level, not native-speaker standards.

What to assess:
1. Accuracy: Did the student correctly transfer the meaning?
2. Nuance: Did the student capture tone, implication, or shades of meaning when reasonable for this level?
3. Completeness: Did the student include the important content?{accent_instruction}

Scoring guidance:
- Be encouraging but honest.
- Do not over-penalize learners for natural beginner omissions that are beyond their level.
- At lower levels, prioritize core meaning over polished phrasing.
- At higher levels, expect more precision and nuance.

Return valid JSON only with exactly this structure:
{{
    "score": <number 0-100>,
    "accuracy": "Assessment of meaning accuracy",
    "nuance": "Assessment of nuance and tone capture",
    "completeness": "Assessment of completeness",
    "suggestions": "Specific, level-appropriate suggestions for improvement",
    "corrected_translation": "A natural English translation of the source text"
}}"""


def assess_translation_user_prompt(adapted_text: str, user_translation: str) -> str:
    """User prompt for translation assessment."""
    return f"""SOURCE TEXT:
{adapted_text}

STUDENT TRANSLATION:
{user_translation}

Assess the student's translation according to the required JSON schema."""


def generate_questions_system_prompt(language_code: str, level: str) -> str:
    """System prompt for generating comprehension questions."""
    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    level_desc = CEFR_DESCRIPTIONS.get(level, "Intermediate level")

    return f"""You are a language teacher creating comprehension questions in {lang_name} for a CEFR {level} student.

Level guidance:
{level_desc}

Goal:
Create questions that the student can realistically answer at their level while reinforcing reading comprehension and output in {lang_name}.

Rules:
1. Write all questions in {lang_name}.
2. Base the questions only on the text provided.
3. Make the difficulty truly match CEFR {level}.
4. expected_answer_hint must be in English.
5. Avoid trick questions.
6. Keep wording simple enough for the learner level.

Difficulty by level:
- pre-A1a: only yes/no, either/or, or single-word questions; focus on recognizing basic words.
- pre-A1b: mostly yes/no, either/or, or one- to two-word questions.
- A1: simple factual questions answerable with one word, a short phrase, or a very short sentence.
- A2: simple factual and personal-reaction questions answerable with short phrases or short sentences.
- B1: mostly open questions requiring 1-2 sentences; include simple inference or opinion.
- B2+: open-ended questions are fine; include inference, opinion, and interpretation.
7. Generate a mix appropriate to the level, but do not force advanced question types for beginners.
8. Keep each question short and clear.

Return valid JSON only with exactly this structure:
{{
    "questions": [
        {{"question": "Question in {lang_name}", "expected_answer_hint": "Brief English hint"}},
        ...
    ]
}}"""


def generate_questions_user_prompt(adapted_text: str, num_questions: int) -> str:
    """User prompt for question generation."""
    return f"""Create exactly {num_questions} comprehension questions based only on the text below.

TEXT:
{adapted_text}

Requirements:
- Generate exactly {num_questions} questions.
- Match the learner level.
- Return valid JSON only."""


def assess_answer_system_prompt(
    language_code: str, level: str, ignore_accents: bool = True
) -> str:
    """System prompt for assessing a student's answer to a comprehension question."""
    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    lang_info = get_language_info(language_code)

    accent_instruction = ""
    if ignore_accents and lang_info:
        if lang_info.script == "latin":
            accent_instruction = "\nAccent policy: Missing accents alone should not reduce the score unless they create confusion."

    return f"""You are a {lang_name} language teacher assessing a student's answer to a comprehension question.

The student is CEFR level {level}. Evaluate according to that level, not native-speaker standards.

Assess:
1. Correctness: Is the answer factually supported by the text?
2. Grammar: Is the grammar appropriate for this learner's level?
3. Vocabulary: Is the vocabulary appropriate and understandable for this level?{accent_instruction}

Scoring guidance:
- Prioritize meaning first.
- For lower levels, do not over-penalize short or telegraphic answers if they are correct.
- For higher levels, expect more complete and accurate language.
- Be encouraging but specific.
- Correct only what matters most.

Return valid JSON only with exactly this structure:
{{
    "score": <number 0-100>,
    "correctness": "Assessment of factual correctness",
    "grammar": "Assessment of grammar for this level",
    "feedback": "Brief, specific, encouraging feedback with corrections if needed"
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

STUDENT ANSWER:
{user_answer}

Assess the answer according to the required JSON schema."""
