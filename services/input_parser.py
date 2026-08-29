"""
Input Parser (Logic Layer, box 1 in your architecture diagram).

One shared function validates and cleans feedback data no matter which
channel it came from — web form, CSV row, or API POST. This is what makes
the "multi-channel" design possible: every channel just builds a dict and
hands it to this same function.
"""

ALLOWED_CATEGORIES = {
    "Mobile Phones", "Home Appliances", "Electronics", "Computers & Laptops",
    "Accessories", "Software / Applications", "Delivery", "Customer Support",
    "Payment / Billing", "Other",
}
ALLOWED_CHANNELS = {"web", "qr", "csv", "api"}
ALLOWED_RATINGS = {x / 2 for x in range(0, 11)}  # 0, 0.5, 1, 1.5 ... 5.0
MAX_REVIEW_WORDS = 250  # item 6: backend-enforced word limit, mirrors the frontend counter


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
    category = (data.get("category") or "Other").strip()

    # --- Required fields ---
    # customer_name/contact are auto-filled server-side from the logged-in
    # session for the web channel (item 4 — no longer typed by the customer),
    # but CSV/API submissions still need to supply them explicitly.
    if not customer_name:
        errors.append("Customer name is required.")
    if not contact:
        errors.append("Contact information is required.")
    if not product_service:
        errors.append("Product name is required.")

    if not review_text:
        errors.append("Review text is required.")
    else:
        word_count = len(review_text.split())
        if word_count < 3:
            errors.append("Review text is too short to be useful.")
        elif word_count > MAX_REVIEW_WORDS:
            # Item 6: backend enforcement — cannot be bypassed by editing
            # the frontend counter or sending a raw request.
            errors.append(f"Review exceeds the {MAX_REVIEW_WORDS}-word limit ({word_count} words submitted).")

    # --- Rating (item 1: 0–5 in 0.5 increments) ---
    try:
        rating = float(data.get("rating"))
        # snap to nearest 0.5 to absorb minor float rounding, then validate range
        rating = round(rating * 2) / 2
        if rating not in ALLOWED_RATINGS:
            errors.append("Rating must be between 0 and 5, in 0.5 increments.")
    except (TypeError, ValueError):
        errors.append("Rating must be a number between 0 and 5.")
        rating = None

    # --- Category (item 2: fixed dropdown, no arbitrary text) ---
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
