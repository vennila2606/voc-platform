import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from config import Config
from models import db, Admin, Customer


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "customer_login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # user_id looks like "admin-3" or "customer-7"
        kind, _, raw_id = user_id.partition("-")
        if kind == "admin":
            return Admin.query.get(int(raw_id))
        if kind == "customer":
            return Customer.query.get(int(raw_id))
        return None

    register_routes(app)

    os.makedirs(os.path.join(os.path.dirname(__file__), "instance"), exist_ok=True)
    with app.app_context():
        db.create_all()

    return app


def admin_required(role=None):
    """Decorator: only logged-in Admins (optionally a specific role) may pass."""
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not isinstance(current_user, Admin):
                flash("Admin access required.", "error")
                return redirect(url_for("admin_login"))
            if role and current_user.role != role:
                flash("You don't have permission to view that page.", "error")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def register_routes(app):

    # ---------- Public ----------
    @app.route("/")
    def index():
        # Static placeholder stats — Week 6 wires these to real KPI queries
        stats = {
            "reviews_collected": 24891,
            "voice_health_score": "74 / 100",
            "avg_response_time": "< 4 hrs",
            "issues_resolved": "89%",
        }
        return render_template("index.html", stats=stats)

    # ---------- Admin auth ----------
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "admin")

            admin = Admin.query.filter_by(username=username).first()
            if admin and admin.check_password(password) and admin.role == role:
                login_user(admin)
                flash("Welcome back!", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid credentials or role.", "error")
        return render_template("admin_login.html")

    # ---------- Customer auth ----------
    @app.route("/customer/login", methods=["GET", "POST"])
    def customer_login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            customer = Customer.query.filter_by(email=email).first()
            if customer and customer.check_password(password):
                login_user(customer)
                flash("Signed in successfully.", "success")
                return redirect(url_for("give_feedback"))
            flash("Invalid email or password.", "error")
        return render_template("customer_portal.html", active_tab="signin")

    @app.route("/customer/register", methods=["POST"])
    def customer_register():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return render_template("customer_portal.html", active_tab="register")

        if Customer.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_template("customer_portal.html", active_tab="register")

        customer = Customer(name=name, email=email)
        customer.set_password(password)
        db.session.add(customer)
        db.session.commit()

        login_user(customer)
        flash("Account created — welcome!", "success")
        return redirect(url_for("give_feedback"))

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You've been logged out.", "success")
        return redirect(url_for("index"))

    # ---------- Placeholders for Week 3+ ----------
    @app.route("/feedback/new")
    @login_required
    def give_feedback():
        # Full feedback form ships in Week 3
        return render_template("feedback_stub.html")

    @app.route("/dashboard")
    @admin_required()
    def dashboard():
        # Real dashboard ships in Week 6
        return render_template("dashboard_stub.html")


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
