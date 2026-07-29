"""
Review Authenticity Verification (Intelligence Layer, box 1 in your diagram).
Checks: duplicate content, spam-like wording, repeated submissions from the
same contact in a short window, and other suspicious patterns.

This runs against the database, so it takes the Feedback model + a db
session rather than being a pure function like input_parser/quality.
"""
from datetime import datetime, timedelta
from difflib import SequenceMatcher

SPAM_MARKERS = ["http://", "https://", "www.", "click here", "buy now", "free money"]
DUPLICATE_SIMILARITY_THRESHOLD = 0.9
REPEAT_SUBMISSION_WINDOW_MINUTES = 10
REPEAT_SUBMISSION_LIMIT = 3


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def check_authenticity(Feedback, db, customer_name, contact, review_text):
    """
    Returns (is_authentic: bool, reasons: list[str]).
    Any single strong signal (spam, near-duplicate) marks it inauthentic.
    Multiple weaker signals (repeat submissions) can combine.
    """
    reasons = []

    # 1. Spam-like wording
    lowered = review_text.lower()
    if any(marker in lowered for marker in SPAM_MARKERS):
        reasons.append("Contains spam-like content (links or promotional phrases).")

    # 2. Duplicate / near-duplicate content across all feedback
    recent_reviews = (
        Feedback.query.order_by(Feedback.created_at.desc()).limit(500).all()
    )
    for existing in recent_reviews:
        if _similar(existing.review_text, review_text) >= DUPLICATE_SIMILARITY_THRESHOLD:
            reasons.append("Very similar to an existing review (possible duplicate).")
            break

    # 3. Repeated submissions from the same contact in a short window
    window_start = datetime.utcnow() - timedelta(minutes=REPEAT_SUBMISSION_WINDOW_MINUTES)
    recent_count = Feedback.query.filter(
        Feedback.contact == contact,
        Feedback.created_at >= window_start,
    ).count()
    if recent_count >= REPEAT_SUBMISSION_LIMIT:
        reasons.append(
            f"More than {REPEAT_SUBMISSION_LIMIT} submissions from this contact in "
            f"{REPEAT_SUBMISSION_WINDOW_MINUTES} minutes (unusual behavior)."
        )

    is_authentic = len(reasons) == 0
    return is_authentic, reasons
