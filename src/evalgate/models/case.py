"""Case and dataset models.

A case is one row of a golden dataset. Case ids are stable and unique within a suite;
they are the join key for baseline diffs and judge caching.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Case(BaseModel):
    """A single evaluation case.

    ``expected`` is intentionally free-form: metrics that need a machine-comparable
    expectation (``exact_match``) compare against it directly, and judges receive it as
    reference facts.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=128)
    input: str = Field(min_length=1)
    expected: str | None = None
    context: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            message = "case id must not contain whitespace"
            raise ValueError(message)
        return value

    @field_validator("tags")
    @classmethod
    def _deduplicate_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))
