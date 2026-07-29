import os
import io
import csv
import uuid
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from config import Config
from models import db, Admin, Customer, Feedback
from services.input_parser import parse_feedback_input
from services.quality import analyze_quality
from services.authenticity import check_authenticity
from services.ai_analysis import run_ai_pipeline

ALLOWED_UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB, matches the "up to 5 MB" text on the form
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def _save_proof_file(file_storage):
    """Validates and saves an uploaded proof file. Returns the relative path
    to store on the Feedback row, or None if no valid file was provided."""
    if not file_storage or not file_storage.filename:
        return None

    if not _allowed_file(file_storage.filename):
        raise ValueError("Only PNG, JPG, or PDF files are allowed.")

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_UPLOAD_SIZE_BYTES:
        raise ValueError("File is larger than 5 MB.")

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    original = secure_filename(file_storage.filename)
    unique_name = f"{uuid.uuid4().hex}_{original}"
    file_storage.save(os.path.join(UPLOAD_FOLDER, unique_name))
    return f"uploads/{unique_name}"


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

    # ---------- Week 3: Feedback Collection ----------

    def _save_feedback(cleaned: dict, customer_id=None, proof_image_path=None):
        """Shared 'Data Manager' step — runs quality, authenticity, and AI
        analysis, then stores the row. Used by web form, CSV import, and API."""
        quality_score, quality_notes = analyze_quality(cleaned["review_text"])
        is_authentic, auth_reasons = check_authenticity(
            Feedback, db,
            cleaned["customer_name"], cleaned["contact"], cleaned["review_text"],
        )
        ai_results = run_ai_pipeline(
            cleaned["review_text"], cleaned["rating"], cleaned["category"]
        )

        fb = Feedback(
            customer_id=customer_id,
            customer_name=cleaned["customer_name"],
            contact=cleaned["contact"],
            product_service=cleaned["product_service"],
            rating=cleaned["rating"],
            category=cleaned["category"],
            review_text=cleaned["review_text"],
            channel=cleaned["channel"],
            quality_score=quality_score,
            is_authentic=is_authentic,
            authenticity_notes="; ".join(auth_reasons) if auth_reasons else None,
            proof_image_path=proof_image_path,
            sentiment=ai_results["sentiment"],
            sentiment_score=ai_results["sentiment_score"],
            emotion=ai_results["emotion"],
            intent=ai_results["intent"],
            topic=ai_results["topic"],
            priority=ai_results["priority"],
        )
        db.session.add(fb)
        db.session.commit()
        return fb, quality_notes

    @app.route("/feedback/new", methods=["GET", "POST"])
    @login_required
    def give_feedback():
        if request.method == "POST":
            raw = {
                "customer_name": request.form.get("customer_name"),
                "contact": request.form.get("contact"),
                "product_service": request.form.get("product_service"),
                "rating": request.form.get("rating"),
                "category": request.form.get("category"),
                "review_text": request.form.get("review_text"),
            }
            cleaned, errors = parse_feedback_input(raw, channel="web")
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("feedback_form.html")

            try:
                proof_path = _save_proof_file(request.files.get("proof_file"))
            except ValueError as e:
                flash(str(e), "error")
                return render_template("feedback_form.html")

            customer_id = current_user.id if isinstance(current_user, Customer) else None
            fb, _ = _save_feedback(cleaned, customer_id=customer_id, proof_image_path=proof_path)
            return render_template("feedback_success.html", name=fb.customer_name)

        return render_template("feedback_form.html")

    # QR code — points at the same feedback form, tagged with channel=qr
    @app.route("/feedback/qr")
    @login_required
    def feedback_qr():
        feedback_url = url_for("give_feedback", _external=True)
        return render_template("feedback_qr.html", feedback_url=feedback_url)

    @app.route("/feedback/qr.png")
    def feedback_qr_image():
        import qrcode
        feedback_url = url_for("give_feedback", _external=True)
        img = qrcode.make(feedback_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    # CSV import — admin only
    @app.route("/admin/feedback/import", methods=["GET", "POST"])
    @admin_required()
    def admin_feedback_import():
        results = None
        if request.method == "POST":
            file = request.files.get("csv_file")
            if not file or not file.filename.endswith(".csv"):
                flash("Please upload a .csv file.", "error")
                return render_template("csv_import.html")

            stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
            reader = csv.DictReader(stream)

            success_count = 0
            errors = []
            for i, row in enumerate(reader, start=2):  # row 1 = header
                cleaned, row_errors = parse_feedback_input(row, channel="csv")
                if row_errors:
                    errors.append({"row": i, "message": "; ".join(row_errors)})
                    continue
                _save_feedback(cleaned)
                success_count += 1

            results = {"success": success_count, "errors": errors}

        return render_template("csv_import.html", results=results)

    # API endpoint — "API-ready design" for external systems
    @app.route("/api/feedback", methods=["POST"])
    def api_feedback():
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Request body must be JSON."}), 400

        cleaned, errors = parse_feedback_input(data, channel="api")
        if errors:
            return jsonify({"error": "Validation failed.", "details": errors}), 422

        fb, quality_notes = _save_feedback(cleaned)
        return jsonify({
            "id": fb.id,
            "status": "stored",
            "is_authentic": fb.is_authentic,
            "quality_score": fb.quality_score,
            "quality_notes": quality_notes,
        }), 201

    @app.route("/dashboard")
    @admin_required()
    def dashboard():
        # Real dashboard ships in Week 6
        return render_template("dashboard_stub.html")

    # ---------- Admin Manager: create/manage admin accounts + roles ----------
    # Restricted to role="admin" only — managers/agents can't touch this.
    @app.route("/admin/users")
    @admin_required(role="admin")
    def admin_users():
        all_admins = Admin.query.order_by(Admin.created_at.desc()).all()
        return render_template("admin_users.html", admins=all_admins)

    @app.route("/admin/users/new", methods=["POST"])
    @admin_required(role="admin")
    def admin_users_new():
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "agent")
        department = request.form.get("department", "").strip()

        if role not in {"admin", "manager", "agent"}:
            flash("Invalid role selected.", "error")
            return redirect(url_for("admin_users"))

        if not username or not email or not password:
            flash("Username, email, and password are all required.", "error")
            return redirect(url_for("admin_users"))

        if Admin.query.filter((Admin.username == username) | (Admin.email == email)).first():
            flash("An admin with that username or email already exists.", "error")
            return redirect(url_for("admin_users"))

        new_admin = Admin(username=username, email=email, role=role, department=department or None)
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()

        flash(f"Created {role} account for {username}.", "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/<int:admin_id>/role", methods=["POST"])
    @admin_required(role="admin")
    def admin_users_update_role(admin_id):
        target = Admin.query.get_or_404(admin_id)
        new_role = request.form.get("role")

        if new_role not in {"admin", "manager", "agent"}:
            flash("Invalid role.", "error")
            return redirect(url_for("admin_users"))

        if target.id == current_user.id and new_role != "admin":
            flash("You can't remove your own admin role.", "error")
            return redirect(url_for("admin_users"))

        target.role = new_role
        db.session.commit()
        flash(f"Updated {target.username}'s role to {new_role}.", "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/<int:admin_id>/delete", methods=["POST"])
    @admin_required(role="admin")
    def admin_users_delete(admin_id):
        target = Admin.query.get_or_404(admin_id)

        if target.id == current_user.id:
            flash("You can't delete your own account.", "error")
            return redirect(url_for("admin_users"))

        db.session.delete(target)
        db.session.commit()
        flash(f"Removed {target.username}.", "success")
        return redirect(url_for("admin_users"))


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
