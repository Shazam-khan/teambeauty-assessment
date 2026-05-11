"""Cheap, deterministic English vs Urdu detection.

Urdu is written in the Perso-Arabic script. We check what fraction of the
*letter* characters in a message fall in the Arabic/Urdu Unicode blocks.
If that fraction is high, it's Urdu; otherwise English. Numbers,
punctuation, and emoji are ignored.

This is intentionally not LLM-based: it has to be fast, free, and
predictable, and we want to pass the detected language into the model's
system prompt rather than ask the model to guess.
"""
from __future__ import annotations


def _is_perso_arabic(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x0600 <= cp <= 0x06FF       # Arabic
        or 0x0750 <= cp <= 0x077F    # Arabic Supplement
        or 0xFB50 <= cp <= 0xFDFF    # Arabic Presentation Forms-A
        or 0xFE70 <= cp <= 0xFEFF    # Arabic Presentation Forms-B
    )


def detect_language(text: str) -> str:
    """Return 'ur' or 'en'. Defaults to 'en' when undecidable."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    urdu = sum(1 for c in letters if _is_perso_arabic(c))
    return "ur" if urdu / len(letters) >= 0.3 else "en"
