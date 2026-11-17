"""Text formatting helpers (Appendix C; description paragraphs per 10.3)."""

from __future__ import annotations

_URL_LABELS: dict[str, str] = {
    "homepage": "Website",
    "bugtracker": "Report a problem",
    "help": "Help",
    "faq": "FAQ",
    "donation": "Donate",
    "translate": "Translate",
    "contact": "Contact",
    "vcs-browser": "Source code",
    "contribute": "Contribute",
}


def paragraphs(description: str) -> list[str]:
    """Split a description into non-empty paragraphs on ``\\n``."""
    return [part.strip() for part in (description or "").split("\n") if part.strip()]


def url_labels(urls: dict[str, str] | None) -> list[tuple[str, str]]:
    """Return ``(label, url)`` pairs for clickable ``https://`` URLs (Appendix C).

    Only ``https://`` links are shown. Known keys get their Appendix C label;
    unknown keys are title-cased with ``-``/``_`` replaced by spaces.
    """
    result: list[tuple[str, str]] = []
    for key, url in (urls or {}).items():
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        label = _URL_LABELS.get(key)
        if label is None:
            label = key.replace("-", " ").replace("_", " ").title()
        result.append((label, url))
    return result
