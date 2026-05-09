"""Credential and sensitive data redaction before writing to audit/candidate files.

Ported from Evolver's gep/sanitize.js (JS regex → Python re).
"""

import re
from typing import Pattern

# ── Redaction patterns ──
# Each pattern is compiled once and applied in order.

_PATTERNS: list[tuple[Pattern[str], str]] = [
    # API keys (OpenAI, Anthropic, etc.)
    (re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bant-api\d{2}-[a-zA-Z0-9\-_]{20,}\b"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"\bglpat-[a-zA-Z0-9\-_]{20,}\b"), "[REDACTED_GITLAB_TOKEN]"),
    (re.compile(r"\bghp_[a-zA-Z0-9]{36}\b"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"\bgho_[a-zA-Z0-9]{36}\b"), "[REDACTED_GITHUB_OAUTH]"),
    (re.compile(r"\bgithub_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}\b"), "[REDACTED_GITHUB_PAT]"),

    # AWS credentials
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_SESSION_KEY]"),

    # Generic bearer tokens
    (re.compile(r"\bBearer\s+[a-zA-Z0-9_\-\.]{20,}\b"), "[REDACTED_BEARER_TOKEN]"),

    # Email addresses
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[REDACTED_EMAIL]"),

    # IP addresses
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[REDACTED_IP]"),

    # Private paths (home directories)
    (re.compile(r"/home/[a-zA-Z0-9_]+"), "[REDACTED_HOME_PATH]"),
    (re.compile(r"/Users/[a-zA-Z0-9_]+"), "[REDACTED_HOME_PATH]"),
    (re.compile(r"C:\\\\Users\\\\[a-zA-Z0-9_]+"), "[REDACTED_HOME_PATH]"),
]


def sanitize(text: str) -> str:
    """Redact sensitive data from text.

    Returns the sanitized string. If no patterns match, returns the original.
    """
    if not text:
        return text
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def sanitize_dict(obj: dict) -> dict:
    """Recursively sanitize all string values in a dict."""
    result = {}
    for key, value in obj.items():
        if isinstance(value, str):
            result[key] = sanitize(value)
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize(v) if isinstance(v, str) else (sanitize_dict(v) if isinstance(v, dict) else v)
                for v in value
            ]
        else:
            result[key] = value
    return result
