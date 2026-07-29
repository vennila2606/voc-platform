"""
AI Processing Engine (Week 4).

Sentiment analysis uses TextBlob, as specified in the project plan.
Emotion, intent, complaint categorization, and topic clustering are
rule/keyword-based for now — fast, free, and don't need an API key.
These get upgraded to Gemini-backed detection in Week 5, but the output
shape (sentiment/emotion/intent/topic strings on the Feedback row) stays
the same, so nothing downstream needs to change later.
"""
from textblob import TextBlob

# ---------- Sentiment (TextBlob) ----------

def analyze_sentiment(text: str):
    """Returns (sentiment_label, polarity_score -1..1)."""
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity

    if polarity > 0.15:
        label = "Positive"
    elif polarity < -0.15:
        label = "Negative"
    else:
        label = "Neutral"

    return label, round(polarity, 3)


# ---------- Emotion detection (keyword lexicon) ----------

EMOTION_KEYWORDS = {
    "Anger": ["angry", "furious", "unacceptable", "ridiculous", "terrible", "worst", "hate", "disgusted"],
    "Frustration": ["frustrated", "annoying", "again and again", "still not", "keeps happening", "fed up", "waiting"],
    "Disappointment": ["disappointed", "expected better", "let down", "not what i expected", "underwhelmed"],
    "Satisfaction": ["satisfied", "happy", "pleased", "works well", "as expected", "smooth"],
    "Delight": ["amazing", "love", "excellent", "fantastic", "impressed", "exceeded expectations", "best"],
    "Confusion": ["confusing", "not clear", "don't understand", "unclear", "hard to figure out"],
}


def detect_emotion(text: str):
    lowered = text.lower()
    scores = {emotion: 0 for emotion in EMOTION_KEYWORDS}

    for emotion, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                scores[emotion] += 1

    best_emotion = max(scores, key=scores.get)
    if scores[best_emotion] == 0:
        return "Neutral"
    return best_emotion


# ---------- Intent detection ----------

INTENT_KEYWORDS = {
    "Complaint": ["broken", "issue", "problem", "delay", "failed", "not working", "damaged", "wrong", "poor", "bad"],
    "Praise": ["great", "love", "excellent", "amazing", "thank you", "impressed", "fantastic"],
    "Suggestion": ["should", "could you", "it would be better", "please add", "suggest", "recommend adding"],
    "Question": ["?", "how do i", "why does", "when will", "can i"],
    "Refund/Cancellation Request": ["refund", "cancel", "money back", "chargeback"],
}


def detect_intent(text: str, rating: int = None):
    lowered = text.lower()

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return intent

    # Fallback based on rating if no keyword matched
    if rating is not None:
        if rating <= 2:
            return "Complaint"
        if rating >= 4:
            return "Praise"
    return "General Feedback"


# ---------- Complaint categorization / topic clustering ----------
# Keyword clusters map free-text reviews to a consistent topic label,
# which is what feeds "Top Complaint Categories" / "Issue Radar" later.

TOPIC_KEYWORDS = {
    "Delivery Delay": ["late", "delay", "delivery", "shipping", "arrived late", "not delivered"],
    "Payment Failure": ["payment failed", "charged twice", "transaction", "payment", "billing", "refund"],
    "App Crash": ["crash", "app crashed", "freeze", "frozen", "bug", "glitch", "not loading"],
    "Long Wait Times": ["wait", "hold", "queue", "response time", "took forever", "slow response"],
    "Wrong Item": ["wrong item", "incorrect", "different product", "not what i ordered"],
    "Support Quality": ["support", "customer service", "agent", "representative", "help desk"],
    "Product Quality": ["quality", "damaged", "defective", "broken", "poor quality"],
    "Pricing": ["expensive", "overpriced", "price", "cost too much", "not worth"],
}


def detect_topic(text: str, category: str = None):
    lowered = text.lower()

    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return topic

    # Fall back to the manually-selected category if no keyword topic matched
    return category or "General"


# ---------- Priority scoring ----------
# Combines sentiment severity + rating (customer impact) + emotion intensity.
# Frequency-based scoring (how often this topic is trending) comes in
# Week 6 with the Emerging Issue Radar, once there's a time series to compare against.

def calculate_priority(sentiment_label: str, polarity: float, rating: int, emotion: str):
    severity = 0

    if sentiment_label == "Negative":
        severity += 2
    if polarity <= -0.5:
        severity += 1
    if rating is not None and rating <= 2:
        severity += 2
    if emotion in ("Anger", "Frustration"):
        severity += 1

    if severity >= 5:
        return "Critical"
    if severity >= 3:
        return "High"
    if severity >= 1:
        return "Medium"
    return "Low"


def run_ai_pipeline(review_text: str, rating: int, category: str):
    """Single entry point — runs the full AI processing pipeline on one
    piece of feedback and returns everything needed to save the row."""
    sentiment_label, polarity = analyze_sentiment(review_text)
    emotion = detect_emotion(review_text)
    intent = detect_intent(review_text, rating)
    topic = detect_topic(review_text, category)
    priority = calculate_priority(sentiment_label, polarity, rating, emotion)

    return {
        "sentiment": sentiment_label,
        "sentiment_score": polarity,
        "emotion": emotion,
        "intent": intent,
        "topic": topic,
        "priority": priority,
    }
