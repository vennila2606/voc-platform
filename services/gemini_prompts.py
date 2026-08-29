"""
Gemini Prompt Builder (item 3).

Single responsibility: build the exact prompt text sent to Gemini for
single-review analysis, and for the aggregated weekly summary / smart
recommendation engine. Kept separate from the API call and the response
parser so each piece can be tested/changed independently.
"""

REVIEW_ANALYSIS_PROMPT = """You are an AI Customer Feedback Analyst.

Analyze the following customer review. Consider the FULL context — a review
can be positive about one aspect and negative about another (Mixed), so do
not rely on isolated keywords.

Product category: {category}
Product: {product_name}
Rating given: {rating} / 5

Review:
"{review_text}"

Note: the product category above is the TYPE of product (e.g. "Mobile Phones"),
not the type of complaint. Separately identify what the customer's issue is
about (e.g. "Delivery delay", "Battery life") — that is a different thing
from the product category and should go in the "issue" field below. Do NOT
put the product category in the "issue" field.

Return ONLY valid JSON. No explanations, no markdown, no text outside the JSON object.

Fields:
{{
  "sentiment": "Positive/Negative/Neutral/Mixed",
  "sentiment_score": 0.0,
  "emotion": "single word describing the customer's emotional state",
  "intent": "Complaint/Praise/Suggestion/Question/Refund Request/General Feedback",
  "summary": "one short sentence summarizing the customer's experience",
  "issue": "short label for what the ISSUE is about, e.g. Delivery delay, Battery life, Pricing",
  "priority": "Low/Medium/High/Critical",
  "department": "Logistics/Technology/Finance/Customer Success/Operations/Other",
  "recommendation": "one short, actionable business recommendation"
}}

sentiment_score must be a number between -1 and +1.
Return only the JSON object above, with real values filled in.
"""


def build_review_analysis_prompt(review_text: str, category: str = None, product_name: str = None, rating=None) -> str:
    """Item 3/14: builds the per-review analysis prompt, including the
    product category/name/rating for richer context (per item 10's
    product-category-vs-issue-category distinction)."""
    return REVIEW_ANALYSIS_PROMPT.format(
        review_text=review_text,
        category=category or "Not specified",
        product_name=product_name or "Not specified",
        rating=rating if rating is not None else "Not specified",
    )


RECOMMENDATION_ENGINE_PROMPT = """You are a Smart Business Recommendation Engine
for a Voice of Customer platform.

You will be given AGGREGATED statistics across many customer reviews for a
period of time — not individual reviews. Identify the single most significant
issue and recommend a practical business action.

Aggregated data:
{aggregated_stats}

Return ONLY valid JSON in this exact shape:
{{
  "main_issue": "short name of the biggest issue",
  "evidence": "one sentence citing the specific numbers that support this",
  "recommendation": "one or two sentences of practical, actionable advice for management"
}}
"""


def build_recommendation_prompt(aggregated_stats: str) -> str:
    """Item 7: builds the prompt for the aggregated Smart Recommendation Engine."""
    return RECOMMENDATION_ENGINE_PROMPT.format(aggregated_stats=aggregated_stats)


WEEKLY_SUMMARY_PROMPT = """You are an AI Customer Experience Analyst producing a
Weekly Voice of Customer Executive Summary for management.

You are given AGGREGATED statistics for the past week — not individual reviews.

Weekly data:
{weekly_stats}

Return ONLY valid JSON in this exact shape:
{{
  "executive_summary": "2-3 sentence overview of the week's customer experience",
  "key_positive_trends": "what customers liked this week",
  "major_concerns": "the most important negative issues this week",
  "emerging_issues": "issues that are increasing week over week",
  "recommended_actions": "specific actions management should consider",
  "risk_areas": "potential problems that need attention if the trend continues"
}}
"""


def build_weekly_summary_prompt(weekly_stats: str) -> str:
    """Item 13: builds the prompt for the weekly executive summary."""
    return WEEKLY_SUMMARY_PROMPT.format(weekly_stats=weekly_stats)
