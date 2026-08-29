from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Admin(UserMixin, db.Model):
    """Admin / staff users (role-based: admin, manager, agent)."""
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default="admin", nullable=False)  # admin, manager, agent
    department = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        # Prefix so Flask-Login can tell Admin and Customer sessions apart
        return f"admin-{self.id}"


class Customer(UserMixin, db.Model):
    """End customers who submit feedback."""
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    profile_photo = db.Column(db.String(255), nullable=True)  # relative path under static/, None = default avatar
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    feedbacks = db.relationship("Feedback", backref="customer", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f"customer-{self.id}"

    # ---- Profile stats (used by the Customer Profile Panel) ----
    @property
    def total_reviews(self):
        return len(self.feedbacks)

    @property
    def average_rating(self):
        """Supports decimal (half-star) ratings — item 1's requirement
        that dashboard/profile calculations work with 0.5 increments."""
        if not self.feedbacks:
            return None
        ratings = [f.rating for f in self.feedbacks if f.rating is not None]
        return round(sum(ratings) / len(ratings), 1) if ratings else None


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Feedback(db.Model):
    """Stub — built out in Week 3 (Feedback Collection).
    Included now so the DB schema/ERD is finalized in Week 1."""
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    customer_name = db.Column(db.String(120), nullable=False)
    contact = db.Column(db.String(120), nullable=False)
    product_service = db.Column(db.String(150), nullable=False)  # "Product Name" in the form
    rating = db.Column(db.Float, nullable=False)  # 0.0–5.0 in 0.5 increments
    category = db.Column(db.String(50), nullable=True)
    review_text = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(30), default="web")  # web, qr, csv, api

    # Filled in by AI layer — now populated by Gemini API (Week 5), with
    # sentiment/emotion/intent/topic/priority kept from the Week 4 schema
    # so nothing downstream (dashboard, topic breakdown) needs to change.
    sentiment = db.Column(db.String(20), nullable=True)
    sentiment_score = db.Column(db.Float, nullable=True)
    emotion = db.Column(db.String(30), nullable=True)
    intent = db.Column(db.String(50), nullable=True)
    topic = db.Column(db.String(50), nullable=True)
    priority = db.Column(db.String(20), nullable=True)  # Low, Medium, High, Critical
    ai_summary = db.Column(db.Text, nullable=True)
    recommendation = db.Column(db.Text, nullable=True)
    suggested_department = db.Column(db.String(50), nullable=True)
    ai_analysis_source = db.Column(db.String(20), nullable=True)  # "gemini" or "fallback"
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    status = db.Column(db.String(20), default="New")  # New, In Progress, Resolved
    is_authentic = db.Column(db.Boolean, default=True)
    authenticity_notes = db.Column(db.Text, nullable=True)
    quality_score = db.Column(db.Integer, nullable=True)
    proof_image_path = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WeeklySummary(db.Model):
    """Item 13/14: stores each generated executive summary so past ones
    can be viewed later without re-calling Gemini (item 15 efficiency rule)."""
    __tablename__ = "weekly_summaries"

    id = db.Column(db.Integer, primary_key=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    executive_summary = db.Column(db.Text, nullable=True)
    key_positive_trends = db.Column(db.Text, nullable=True)
    major_concerns = db.Column(db.Text, nullable=True)
    emerging_issues = db.Column(db.Text, nullable=True)
    recommended_actions = db.Column(db.Text, nullable=True)
    risk_areas = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    generated_by_admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=True)


class CachedRecommendation(db.Model):
    """Item 7 + 15: Smart Recommendation Engine output, cached so the
    dashboard reads a stored result instead of calling Gemini on every load."""
    __tablename__ = "cached_recommendations"

    id = db.Column(db.Integer, primary_key=True)
    main_issue = db.Column(db.String(150), nullable=True)
    evidence = db.Column(db.Text, nullable=True)
    recommendation = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)


class SalesData(db.Model):
    """Item 18: Silent Customer Detector — sales/activity volume per
    product, imported via CSV. Compared against Feedback row counts to
    compute a feedback rate. This is a structure for importing sales data
    since the platform has no live sales system of its own."""
    __tablename__ = "sales_data"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    sales_count = db.Column(db.Integer, nullable=False)
    period_label = db.Column(db.String(50), nullable=True)  # e.g. "August 2026" — informational only
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)
