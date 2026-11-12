"""Anchored judge prompt construction."""

from __future__ import annotations

from evalgate.constants import JUDGE_MARKER
from evalgate.models.case import Case
from evalgate.providers.base import Completion

_PROMPT = """{marker}
You are a strict evaluator for an LLM quality gate. Score the candidate response against
the rubric below. Ignore writing style, length, and tone unless the rubric says otherwise.
Do not reward confidence. Do not invent requirements that are not in the rubric.

# Rubric
{rubric}

# Case input
{input}

# Policy or reference context
{context}

# Expected facts (if any)
{expected}

# Candidate response
{response}

Return ONLY a JSON object with keys: score, rationale, confidence.
- "score" is an integer from 1 to 5 exactly as defined by the rubric anchors.
- "rationale" is one or two sentences (at most 400 characters) citing the rubric level.
- "confidence" is a number between 0 and 1.
Do not wrap the JSON in prose or code fences.
"""


def build_judge_prompt(*, rubric_text: str, case: Case, response: str) -> str:
    """Render the judge prompt for one case/completion pair."""

    return _PROMPT.format(
        marker=JUDGE_MARKER,
        rubric=rubric_text.strip(),
        input=case.input,
        context=case.context or "(none)",
        expected=case.expected or "(none)",
        response=response,
    )


def judge_prompt_for_completion(*, rubric_text: str, case: Case, completion: Completion) -> str:
    return build_judge_prompt(rubric_text=rubric_text, case=case, response=completion.text)
