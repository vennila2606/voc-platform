"""
Input Parser (Logic Layer, box 1 in your architecture diagram).

One shared function validates and cleans feedback data no matter which
channel it came from — web form, CSV row, or API POST. This is what makes
the "multi-channel" design possible: every channel just builds a dict and
hands it to this same function.
"""

ALLOWED_CATEGORIES = {"Product", "Service", "Delivery", "Support", "Payment", "Other"}
ALLOWED_CHANNELS = {"web", "qr", "csv", "api"}


def parse_feedback_input(data: dict, channel: str = "web"):
    """
    data: dict with keys customer_name, contact, product_service,
          rating, category, review_text
    channel: 'web' | 'qr' | 'csv' | 'api'

    Returns (cleaned_dict, errors_list). If errors_list is non-empty,
    cleaned_dict should not be saved.
    """
    errors = []

    customer_name = (data.get("customer_name") or "").strip()
    contact = (data.get("contact") or "").strip()
    product_service = (data.get("product_service") or "").strip()
    review_text = (data.get("review_text") or "").strip()
    category = (data.get("category") or "Other").strip().title()

    # --- Required fields ---
    if not customer_name:
        errors.append("Customer name is required.")
    if not contact:
        errors.append("Email or mobile is required.")
    if not product_service:
        errors.append("Product or service name is required.")
    if not review_text:
        errors.append("Review text is required.")
    elif len(review_text) < 10:
        errors.append("Review text is too short to be useful (min 10 characters).")

    # --- Rating ---
    try:
        rating = int(data.get("rating"))
        if rating < 1 or rating > 5:
            errors.append("Rating must be between 1 and 5.")
    except (TypeError, ValueError):
        errors.append("Rating must be a whole number from 1 to 5.")
        rating = None

    # --- Category ---
    if category not in ALLOWED_CATEGORIES:
        category = "Other"

    # --- Channel ---
    if channel not in ALLOWED_CHANNELS:
        channel = "web"

    # --- Basic normalization / cleaning ---
    customer_name = " ".join(customer_name.split())  # collapse extra whitespace
    review_text = " ".join(review_text.split())

    cleaned = {
        "customer_name": customer_name,
        "contact": contact,
        "product_service": product_service,
        "rating": rating,
        "category": category,
        "review_text": review_text,
        "channel": channel,
    }

    return cleaned, errors
