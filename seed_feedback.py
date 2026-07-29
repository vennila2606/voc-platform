"""
Generates realistic sample feedback data so you can test the dashboard,
charts, and analytics features without typing entries by hand.

Run:
    python seed_feedback.py            # adds 100 sample rows
    python seed_feedback.py 250        # adds a custom number of rows
"""
import sys
import random
from datetime import datetime, timedelta

from app import create_app
from models import db, Feedback, Customer

PRODUCTS = [
    "Mobile App", "Delivery Service", "Customer Support", "Payment Gateway",
    "Subscription Plan", "Website Checkout", "Loyalty Program", "Live Chat Support",
]
CATEGORIES = ["Product", "Service", "Delivery", "Support", "Payment", "Other"]
CHANNELS = ["web", "qr", "csv", "api"]

POSITIVE_TEXTS = [
    "Really happy with how smooth the experience was, will use again.",
    "Great support team, resolved my issue in minutes.",
    "Delivery arrived earlier than expected, very impressed.",
    "The app is intuitive and easy to navigate.",
    "Excellent value for the price, exceeded expectations.",
]
NEUTRAL_TEXTS = [
    "It was okay, nothing special but got the job done.",
    "Average experience, some things could be improved.",
    "Works as expected, no major complaints.",
]
NEGATIVE_TEXTS = [
    "Delivery was delayed by several days with no updates.",
    "Payment failed twice before finally going through.",
    "Support took too long to respond to my ticket.",
    "The app crashed while I was checking out.",
    "Product quality did not match the description.",
]

FIRST_NAMES = ["Raj", "Priya", "Amit", "Neha", "Vikram", "Sunita", "Arjun", "Kavya", "Rohan", "Anita"]
LAST_NAMES = ["Kumar", "Sharma", "Singh", "Patel", "Mehta", "Rao", "Nair", "Gupta", "Iyer", "Verma"]


def random_review():
    bucket = random.choices(
        ["positive", "neutral", "negative"], weights=[0.5, 0.2, 0.3]
    )[0]
    if bucket == "positive":
        return random.choice(POSITIVE_TEXTS), random.randint(4, 5), "Positive"
    if bucket == "neutral":
        return random.choice(NEUTRAL_TEXTS), 3, "Neutral"
    return random.choice(NEGATIVE_TEXTS), random.randint(1, 2), "Negative"


def generate(count):
    app = create_app()
    with app.app_context():
        existing_customers = Customer.query.all()
        created = 0

        for _ in range(count):
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            email = f"{name.lower().replace(' ', '.')}{random.randint(1,999)}@example.com"
            review_text, rating, sentiment = random_review()
            days_ago = random.randint(0, 30)

            fb = Feedback(
                customer_id=random.choice(existing_customers).id if existing_customers and random.random() > 0.5 else None,
                customer_name=name,
                contact=email,
                product_service=random.choice(PRODUCTS),
                rating=rating,
                category=random.choice(CATEGORIES),
                review_text=review_text,
                channel=random.choice(CHANNELS),
                sentiment=sentiment,
                priority=random.choice(["Low", "Medium", "High", "Critical"]) if sentiment == "Negative" else "Low",
                status=random.choice(["New", "In Progress", "Resolved"]),
                created_at=datetime.utcnow() - timedelta(days=days_ago),
            )
            db.session.add(fb)
            created += 1

        db.session.commit()
        print(f"Inserted {created} sample feedback rows.")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    generate(n)
