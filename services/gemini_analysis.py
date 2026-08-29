"""
Gemini API Client (item 1, 2, 6).

This is the ONLY module that makes network calls to Gemini. It is
intentionally thin: build prompt -> call API -> hand response to parser ->
return clean dict. Prompt construction lives in gemini_prompts.py,
validation lives in gemini_parser.py — kept separate per items 3/4.

Item 2 (security): the API key is read from the GEMINI_API_KEY environment
variable only (via .env locally). It is never hard-coded, never sent to
the frontend, and never logged. This file runs exclusively in the Flask
backend — the browser/JS never talks to Gemini directly.

Item 6 (failure handling): every possible failure mode (missing key,
timeout, network error, invalid JSON, rate limit) is caught here and
converted to a safe fallback result. The calling code in app.py never
needs its own try/except for Gemini — this file guarantees it never raises.
"""
import os
import logging
import requests

from services.gemini_prompts import build_review_analysis_prompt, build_recommendation_prompt, build_weekly_summary_prompt
from services.gemini_parser import (
    parse_review_analysis, parse_recommendation, parse_weekly_summary, GeminiParseError,
)

logger = logging.getLogger("voc.gemini")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "30"))


def _fallback_result(reason: str):
    """Item 6: safe, neutral result used whenever Gemini can't be reached.
    The technical reason is logged for the admin (server console / log
    file) but never shown to the customer submitting feedback."""
    logger.warning("Gemini analysis fell back to neutral default: %s", reason)
    return {
        "sentiment": "Neutral",
        "sentiment_score": 0.0,
        "emotion": "Unknown",
        "intent": "General Feedback",
        "topic": None,
        "summary": "AI analysis unavailable — showing neutral default.",
        "priority": "Medium",
        "suggested_department": "Other",
        "recommendation": None,
        "source": "fallback",
        "fallback_reason": reason,
    }


def _call_gemini(prompt: str):
    """Raw API call — raises on any failure, caught by callers below.
    Item 2: key is only ever read from the environment and only ever
    sent as a request parameter to Google's API, never logged or returned."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured")

    response = requests.post(
        GEMINI_URL,
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                # This is a quick classification task, not one needing deep
                "thinkingConfig": {"thinkingBudget": 0},
            },
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def analyze_with_gemini(review_text: str, category: str = None, product_name: str = None, rating=None):
    """Item 1: single-review contextual analysis. Never raises."""
    try:
        prompt = build_review_analysis_prompt(review_text, category=category, product_name=product_name, rating=rating)
        raw_text = _call_gemini(prompt)
        return parse_review_analysis(raw_text, fallback_category=category)

    except requests.exceptions.Timeout:
        return _fallback_result("Gemini API request timed out")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        if status == 429:
            return _fallback_result("Gemini API rate limit / quota exceeded")
        return _fallback_result(f"Gemini API HTTP error ({status})")
    except requests.exceptions.RequestException as e:
        return _fallback_result(f"Gemini API network error: {e}")
    except GeminiParseError as e:
        return _fallback_result(str(e))
    except RuntimeError as e:
        return _fallback_result(str(e))
    except Exception as e:  # last-resort guard — never let this crash a submission
        logger.exception("Unexpected error during Gemini analysis")
        return _fallback_result(f"unexpected error: {e}")


def run_ai_pipeline(review_text: str, rating, category: str, product_name: str = None):
    """Entry point used by app.py's _save_feedback(). Same output shape
    regardless of success/fallback, so the caller never needs to branch."""
    result = analyze_with_gemini(review_text, category=category, product_name=product_name, rating=rating)
    if not result.get("topic"):
        result["topic"] = category or "General"
    return result


def generate_recommendation(aggregated_stats_text: str):
    """Item 7: Smart Recommendation Engine — call Gemini ONCE with
    pre-aggregated stats (never raw reviews), per item 15's efficiency rule."""
    try:
        prompt = build_recommendation_prompt(aggregated_stats_text)
        raw_text = _call_gemini(prompt)
        return parse_recommendation(raw_text)
    except Exception as e:
        logger.warning("Recommendation engine fell back: %s", e)
        return {
            "main_issue": "AI recommendation unavailable",
            "evidence": "",
            "recommendation": "Gemini could not be reached — check API key/quota and try again.",
        }


def generate_weekly_summary(weekly_stats_text: str):
    """Item 13: Weekly Executive Summary — call Gemini ONCE with
    pre-aggregated weekly stats, never individual reviews."""
    try:
        prompt = build_weekly_summary_prompt(weekly_stats_text)
        raw_text = _call_gemini(prompt)
        return parse_weekly_summary(raw_text)
    except Exception as e:
        logger.warning("Weekly summary generation fell back: %s", e)
        return {
            "executive_summary": "AI summary unavailable — Gemini could not be reached.",
            "key_positive_trends": "",
            "major_concerns": "",
            "emerging_issues": "",
            "recommended_actions": "",
            "risk_areas": "",
        }
