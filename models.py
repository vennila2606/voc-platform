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
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    feedbacks = db.relationship("Feedback", backref="customer", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f"customer-{self.id}"


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
    product_service = db.Column(db.String(150), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50), nullable=True)  # Product, Service, Delivery, Support, Payment, Other
    review_text = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(30), default="web")  # web, qr, csv, api

    # Filled in by AI layer (Week 4/5) — nullable for now
    sentiment = db.Column(db.String(20), nullable=True)
    sentiment_score = db.Column(db.Float, nullable=True)
    emotion = db.Column(db.String(30), nullable=True)
    intent = db.Column(db.String(50), nullable=True)
    topic = db.Column(db.String(50), nullable=True)
    priority = db.Column(db.String(20), nullable=True)  # Low, Medium, High, Critical
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    status = db.Column(db.String(20), default="New")  # New, In Progress, Resolved
    is_authentic = db.Column(db.Boolean, default=True)
    authenticity_notes = db.Column(db.Text, nullable=True)
    quality_score = db.Column(db.Integer, nullable=True)
    proof_image_path = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
