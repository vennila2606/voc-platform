"""
Review Quality Analyzer.
Lightweight, no external AI calls (that comes in Week 4/5). Flags reviews
that are too short, too repetitive, or too generic to be useful — separate
concern from authenticity (a review can be low quality but still genuine).
"""

GENERIC_PHRASES = {
    "good", "nice", "ok", "okay", "fine", "great", "bad", "test", "testing",
}


def analyze_quality(review_text: str):
    """Returns (quality_score 0-100, notes list)."""
    notes = []
    text = review_text.strip()
    words = text.split()
    word_count = len(words)

    score = 100

    if word_count < 5:
        score -= 40
        notes.append("Very short review — limited detail.")

    if text.lower() in GENERIC_PHRASES:
        score -= 50
        notes.append("Generic single-word review.")

    unique_words = set(w.lower() for w in words)
    if word_count > 0 and len(unique_words) / word_count < 0.4:
        score -= 20
        notes.append("Highly repetitive wording.")

    if not any(c.isalpha() for c in text):
        score -= 60
        notes.append("Review contains no readable text.")

    score = max(0, min(100, score))
    return score, notes
