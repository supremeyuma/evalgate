"""Shared constants that avoid import cycles between packages."""

from __future__ import annotations

#: Marker embedded in the judge prompt so deterministic providers can recognize the task.
JUDGE_MARKER = "EVALGATE_JUDGE_TASK"
