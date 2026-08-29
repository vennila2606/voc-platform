"""
Gemini Response Parser (item 4).

Single responsibility: take Gemini's raw HTTP response, extract the JSON,
validate every field against expected values, and return a clean Python
dict with safe defaults for anything missing or invalid. Nothing gets
stored in SQLite until it has passed through here.

This module never makes network calls and never raises on bad input —
malformed data always degrades to safe defaults rather than crashing.
"""
import json

VALID_SENTIMENTS = {"Positive", "Negative", "Neutral", "Mixed"}
VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}
VALID_CATEGORIES = {
    "Delivery", "Product Quality", "Customer Support", "Payment",
    "Website/App", "Billing", "Other",
}
VALID_INTENTS = {
    "Complaint", "Praise", "Suggestion", "Question",
    "Refund Request", "General Feedback",
}
VALID_DEPARTMENTS = {
    "Logistics", "Technology", "Finance", "Customer Success", "Operations", "Other",
}


class GeminiParseError(Exception):
    """Raised internally when the JSON can't be extracted at all —
    caught by the caller, which substitutes the fallback result."""


def extract_json_text(raw_model_text: str) -> dict:
    """Strips ```json fences (Gemini sometimes adds them despite being
    told not to) and parses the remaining text as JSON."""
    cleaned = raw_model_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).replace("json", "", 1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise GeminiParseError(f"invalid JSON from Gemini: {e}")


def parse_review_analysis(raw_model_text: str, fallback_category: str = None) -> dict:
    """
    Item 4: validates a single-review analysis response.
    Every field is checked against an allowed set; anything missing or
    invalid gets a safe default rather than propagating bad data.
    """
    parsed = extract_json_text(raw_model_text)  # raises GeminiParseError if malformed

    sentiment = parsed.get("sentiment")
    if sentiment not in VALID_SENTIMENTS:
        sentiment = "Neutral"

    priority = parsed.get("priority")
    if priority not in VALID_PRIORITIES:
        priority = "Medium"

    intent = parsed.get("intent")
    if intent not in VALID_INTENTS:
        intent = "General Feedback"

    issue = parsed.get("issue")
    # 'category' here is the AI's classification of the ISSUE/TOPIC being
    # discussed (e.g. "Delivery delay"), which is intentionally separate
    # from the customer's selected PRODUCT category (e.g. "Mobile Phones") —
    # see the distinction documented in gemini_prompts.py. Gemini's answer
    # isn't restricted to a fixed dropdown, so we just guard against empty/
    # non-string values rather than an exact-match allowlist.
    if not issue or not isinstance(issue, str):
        issue = fallback_category or "Other"

    department = parsed.get("department")
    if department not in VALID_DEPARTMENTS:
        department = "Other"

    try:
        sentiment_score = float(parsed.get("sentiment_score", 0.0))
        sentiment_score = max(-1.0, min(1.0, sentiment_score))
    except (TypeError, ValueError):
        sentiment_score = 0.0

    emotion = parsed.get("emotion")
    if not emotion or not isinstance(emotion, str):
        emotion = "Unknown"

    summary = parsed.get("summary")
    if not summary or not isinstance(summary, str):
        summary = None  # non-critical field — allowed to be missing

    recommendation = parsed.get("recommendation")
    if not recommendation or not isinstance(recommendation, str):
        recommendation = None  # non-critical field — allowed to be missing

    return {
        "sentiment": sentiment,
        "sentiment_score": round(sentiment_score, 3),
        "emotion": emotion,
        "intent": intent,
        "topic": issue,  # stored internally as 'topic' (matches existing DB column); this is Gemini's "issue" field
        "summary": summary,
        "priority": priority,
        "suggested_department": department,
        "recommendation": recommendation,
        "source": "gemini",
        "fallback_reason": None,
    }


def parse_recommendation(raw_model_text: str) -> dict:
    """Item 7: validates the aggregated recommendation-engine response."""
    parsed = extract_json_text(raw_model_text)
    return {
        "main_issue": parsed.get("main_issue") or "No dominant issue identified",
        "evidence": parsed.get("evidence") or "",
        "recommendation": parsed.get("recommendation") or "",
    }


def parse_weekly_summary(raw_model_text: str) -> dict:
    """Item 13: validates the weekly executive summary response."""
    parsed = extract_json_text(raw_model_text)
    fields = [
        "executive_summary", "key_positive_trends", "major_concerns",
        "emerging_issues", "recommended_actions", "risk_areas",
    ]
    return {field: (parsed.get(field) or "") for field in fields}
