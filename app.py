import os
import io
import csv
import uuid
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, Response
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from config import Config
from models import db, Admin, Customer, Feedback, WeeklySummary, CachedRecommendation, SalesData
from services.input_parser import parse_feedback_input
from services.quality import analyze_quality
from services.authenticity import check_authenticity
from services.gemini_analysis import run_ai_pipeline, generate_recommendation, generate_weekly_summary
from services import analytics

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

        # Auto-generate a username from the email (e.g. raj.kumar23) so the
        # profile panel always has one, without adding an extra signup field.
        base_username = email.split("@")[0]
        username = base_username
        suffix = 1
        while Customer.query.filter_by(username=username).first():
            suffix += 1
            username = f"{base_username}{suffix}"

        customer = Customer(name=name, email=email, username=username)
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
        analysis, then stores the row. Used by web form, CSV import, and API.
        AI analysis is Gemini-powered; if Gemini is unreachable, run_ai_pipeline
        returns a safe neutral fallback rather than raising, so a submission
        never fails just because the AI call failed."""
        quality_score, quality_notes = analyze_quality(cleaned["review_text"])
        is_authentic, auth_reasons = check_authenticity(
            Feedback, db,
            cleaned["customer_name"], cleaned["contact"], cleaned["review_text"],
        )
        ai_results = run_ai_pipeline(
            cleaned["review_text"], cleaned["rating"], cleaned["category"],
            product_name=cleaned["product_service"],
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
            ai_summary=ai_results.get("summary"),
            recommendation=ai_results.get("recommendation"),
            suggested_department=ai_results.get("suggested_department"),
            ai_analysis_source=ai_results.get("source"),
        )
        db.session.add(fb)
        db.session.commit()

        # Surface to the person submitting if AI analysis silently fell back —
        # transparency without blocking or crashing the submission (item 8).
        if ai_results.get("source") == "fallback":
            flash(
                "Your feedback was saved. AI analysis is temporarily unavailable, "
                "so a neutral status was applied — it can be re-analyzed later.",
                "error",
            )

        return fb, quality_notes

    @app.route("/feedback/new", methods=["GET", "POST"])
    @login_required
    def give_feedback():
        if request.method == "POST":
            # Item 4: name/contact are NOT taken from the form anymore —
            # pulled from the authenticated session instead, so a customer
            # can't type someone else's name/email even if they tried.
            raw = {
                "customer_name": current_user.name if isinstance(current_user, Customer) else "",
                "contact": current_user.email if isinstance(current_user, Customer) else "",
                "product_service": request.form.get("product_service"),
                "rating": request.form.get("rating"),
                "category": request.form.get("category"),
                "review_text": request.form.get("review_text"),
            }
            cleaned, errors = parse_feedback_input(raw, channel="web")
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("feedback_form.html", **_feedback_page_context())

            try:
                proof_path = _save_proof_file(request.files.get("proof_file"))
            except ValueError as e:
                flash(str(e), "error")
                return render_template("feedback_form.html", **_feedback_page_context())

            customer_id = current_user.id if isinstance(current_user, Customer) else None
            fb, _ = _save_feedback(cleaned, customer_id=customer_id, proof_image_path=proof_path)

            # Item 8 + 9: reviews section only appears on the POST-submission
            # confirmation, and only shows the SAME category the customer
            # just submitted — never on the initial GET page load.
            other_reviews = (
                Feedback.query.filter_by(is_authentic=True, category=fb.category)
                .filter(Feedback.id != fb.id)
                .order_by(Feedback.created_at.desc())
                .limit(20)
                .all()
            )
            return render_template(
                "feedback_success.html",
                name=fb.customer_name,
                category=fb.category,
                other_reviews=other_reviews,
            )

        # GET: item 8 — no reviews shown yet, just the form + profile sidebar.
        return render_template("feedback_form.html", **_feedback_page_context())

    def _feedback_page_context():
        """Item 5: the logged-in customer's own profile panel data.
        Item 8: public reviews are deliberately NOT included here — they
        only appear after a successful submission (see give_feedback above)."""
        profile = current_user if isinstance(current_user, Customer) else None
        return {"profile": profile}


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
        """Item 8/9/10/11: the dashboard page itself is just the shell —
        Chart.js pulls real numbers from the /dashboard-data style routes
        below via JS fetch(), so nothing here is hard-coded."""
        filter_options = analytics.get_filter_options()
        latest_recommendation = (
            CachedRecommendation.query.order_by(CachedRecommendation.generated_at.desc()).first()
        )
        latest_summary = (
            WeeklySummary.query.order_by(WeeklySummary.generated_at.desc()).first()
        )
        vhs_trend = analytics.get_voice_health_score_with_trend({})
        emerging = analytics.get_emerging_issues()
        return render_template(
            "dashboard.html",
            filter_options=filter_options,
            latest_recommendation=latest_recommendation,
            latest_summary=latest_summary,
            vhs_trend=vhs_trend,
            emerging_issues=emerging,
        )

    # ---------- Item 8: Dashboard data API routes (JSON, consumed by Chart.js) ----------

    @app.route("/dashboard-data")
    @admin_required()
    def dashboard_data():
        """Single combined payload — KPIs + all chart datasets + insights,
        so the dashboard can do one fetch() on load and on every filter change."""
        args = request.args
        return jsonify({
            "kpis": analytics.get_kpis(args),
            "sentiment_distribution": analytics.get_sentiment_distribution(args),
            "feedback_trend": analytics.get_feedback_trend(args, args.get("granularity", "daily")),
            "sentiment_trend": analytics.get_sentiment_trend(args, args.get("granularity", "daily")),
            "category_distribution": analytics.get_category_distribution(args),
            "priority_distribution": analytics.get_priority_distribution(args),
            "department_distribution": analytics.get_department_distribution(args),
            "insights": analytics.get_smart_insights(args),
        })

    @app.route("/feedback-stats")
    @admin_required()
    def feedback_stats():
        return jsonify(analytics.get_kpis(request.args))

    @app.route("/sentiment-stats")
    @admin_required()
    def sentiment_stats():
        return jsonify(analytics.get_sentiment_distribution(request.args))

    @app.route("/category-stats")
    @admin_required()
    def category_stats():
        return jsonify(analytics.get_category_distribution(request.args))

    @app.route("/trend-data")
    @admin_required()
    def trend_data():
        granularity = request.args.get("granularity", "daily")
        return jsonify({
            "feedback_trend": analytics.get_feedback_trend(request.args, granularity),
            "sentiment_trend": analytics.get_sentiment_trend(request.args, granularity),
        })

    # ---------- Item 7: Smart Recommendation Engine ----------

    @app.route("/admin/recommendation/generate", methods=["POST"])
    @admin_required()
    def generate_recommendation_route():
        """Calls Gemini ONCE with aggregated stats (never raw reviews,
        per item 15), caches the result so it isn't regenerated on every
        dashboard load."""
        stats_text = analytics.build_aggregated_stats_text(request.form or request.args)
        result = generate_recommendation(stats_text)

        rec = CachedRecommendation(
            main_issue=result["main_issue"],
            evidence=result["evidence"],
            recommendation=result["recommendation"],
        )
        db.session.add(rec)
        db.session.commit()

        flash("Recommendation generated.", "success")
        return redirect(url_for("dashboard"))

    # ---------- Item 13/14: Weekly Executive Summary ----------

    @app.route("/admin/weekly-summary/generate", methods=["POST"])
    @admin_required()
    def generate_weekly_summary_route():
        from datetime import date, timedelta as td

        stats_text = analytics.build_weekly_stats_text()
        result = generate_weekly_summary(stats_text)

        summary = WeeklySummary(
            period_start=date.today() - td(days=7),
            period_end=date.today(),
            executive_summary=result["executive_summary"],
            key_positive_trends=result["key_positive_trends"],
            major_concerns=result["major_concerns"],
            emerging_issues=result["emerging_issues"],
            recommended_actions=result["recommended_actions"],
            risk_areas=result["risk_areas"],
            generated_by_admin_id=current_user.id,
        )
        db.session.add(summary)
        db.session.commit()

        flash("Weekly executive summary generated.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/weekly-summary/history")
    @admin_required()
    def weekly_summary_history():
        summaries = WeeklySummary.query.order_by(WeeklySummary.generated_at.desc()).all()
        return render_template("weekly_summary_history.html", summaries=summaries)

    # ---------- Item 18: Silent Customer Detector ----------

    @app.route("/admin/silent-customers")
    @admin_required()
    def silent_customers():
        risks = analytics.get_silent_customer_risks()
        return render_template("silent_customers.html", risks=risks)

    @app.route("/admin/silent-customers/import-sales", methods=["POST"])
    @admin_required()
    def import_sales_data():
        """Item 18: CSV structure for importing sales/activity data, since
        the platform has no live sales system of its own. Expected columns:
        product_name, category, sales_count, period_label (optional)."""
        file = request.files.get("sales_csv")
        if not file or not file.filename.endswith(".csv"):
            flash("Please upload a .csv file.", "error")
            return redirect(url_for("silent_customers"))

        stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
        reader = csv.DictReader(stream)
        imported = 0
        errors = []
        for i, row in enumerate(reader, start=2):
            product_name = (row.get("product_name") or "").strip()
            category = (row.get("category") or "").strip() or None
            period_label = (row.get("period_label") or "").strip() or None
            try:
                sales_count = int(row.get("sales_count"))
            except (TypeError, ValueError):
                errors.append(f"Row {i}: invalid sales_count")
                continue
            if not product_name:
                errors.append(f"Row {i}: product_name is required")
                continue

            db.session.add(SalesData(
                product_name=product_name, category=category,
                sales_count=sales_count, period_label=period_label,
            ))
            imported += 1

        db.session.commit()
        flash(f"Imported {imported} sales records." + (f" {len(errors)} rows had errors." if errors else ""),
              "success" if imported else "error")
        return redirect(url_for("silent_customers"))

    # ---------- Item 19: Emerging Issue Radar ----------

    @app.route("/admin/emerging-issues")
    @admin_required()
    def emerging_issues():
        issues = analytics.get_emerging_issues()
        return render_template("emerging_issues.html", issues=issues)

    @app.route("/emerging-issues-data")
    @admin_required()
    def emerging_issues_data():
        """JSON for the Chart.js visualization on the dashboard/radar page."""
        return jsonify(analytics.get_emerging_issues())

    # ---------- Department-wise Action Queue ----------

    @app.route("/admin/action-queue")
    @admin_required()
    def action_queue():
        status_filter = request.args.get("status") or None
        queue = analytics.get_department_action_queue(status_filter)
        return render_template("action_queue.html", queue=queue, status_filter=status_filter)

    @app.route("/admin/action-queue/update-status", methods=["POST"])
    @admin_required()
    def action_queue_update_status():
        """Authorized admins/managers can update status — bulk-updates every
        feedback row in this (department, issue) group at once."""
        feedback_ids = request.form.get("feedback_ids", "")
        new_status = request.form.get("status")
        if new_status not in {"New", "In Progress", "Resolved"}:
            flash("Invalid status.", "error")
            return redirect(url_for("action_queue"))

        ids = [int(x) for x in feedback_ids.split(",") if x.strip().isdigit()]
        if ids:
            Feedback.query.filter(Feedback.id.in_(ids)).update(
                {"status": new_status}, synchronize_session=False
            )
            db.session.commit()
            flash(f"Updated {len(ids)} feedback item(s) to '{new_status}'.", "success")

        return redirect(url_for("action_queue"))

    # ---------- What-If Simulator ----------

    @app.route("/admin/what-if")
    @admin_required()
    def what_if_simulator():
        issues = analytics.get_issue_list()
        return render_template("what_if_simulator.html", issues=issues)

    @app.route("/what-if-data")
    @admin_required()
    def what_if_data():
        issue = request.args.get("issue")
        try:
            reduction_pct = int(request.args.get("reduction_pct", 50))
        except ValueError:
            reduction_pct = 50
        if not issue:
            return jsonify({"error": "issue parameter is required"}), 400
        result = analytics.simulate_issue_resolution(issue, reduction_pct)
        return jsonify(result)

    # ---------- Feedback Journey Timeline ----------

    @app.route("/admin/journey-timeline")
    @admin_required()
    def journey_timeline_list():
        customers = analytics.get_customers_with_multiple_reviews()
        return render_template("journey_timeline_list.html", customers=customers)

    @app.route("/admin/journey-timeline/<int:customer_id>")
    @admin_required()
    def journey_timeline(customer_id):
        customer = Customer.query.get_or_404(customer_id)
        timeline = analytics.get_customer_journey(customer_id)
        return render_template("journey_timeline.html", customer=customer, timeline=timeline)

    # ---------- Export ----------

    @app.route("/admin/export")
    @admin_required()
    def export_feedback():
        fmt = request.args.get("format", "csv")
        records = analytics.export_feedback_rows(request.args, fmt=fmt)

        if fmt == "json":
            response = jsonify(records)
            response.headers["Content-Disposition"] = "attachment; filename=feedback_export.json"
            return response

        # CSV
        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        else:
            output.write("No data matched the current filters.\n")

        response = Response(output.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=feedback_export.csv"
        return response

    @app.route("/admin/topics")
    @admin_required()
    def admin_topics():
        """
        Groups and counts feedback across the AI-generated fields.
        This is the actual 'clustering/grouping' step — detect_topic() only
        tags one review at a time; this is where those tags get aggregated
        across all feedback, which is what a real dashboard chart needs.
        """
        from sqlalchemy import func

        topic_counts = (
            db.session.query(Feedback.topic, func.count(Feedback.id))
            .group_by(Feedback.topic)
            .order_by(func.count(Feedback.id).desc())
            .all()
        )
        sentiment_counts = (
            db.session.query(Feedback.sentiment, func.count(Feedback.id))
            .group_by(Feedback.sentiment)
            .all()
        )
        priority_counts = (
            db.session.query(Feedback.priority, func.count(Feedback.id))
            .group_by(Feedback.priority)
            .order_by(
                db.case(
                    (Feedback.priority == "Critical", 0),
                    (Feedback.priority == "High", 1),
                    (Feedback.priority == "Medium", 2),
                    (Feedback.priority == "Low", 3),
                    else_=4,
                )
            )
            .all()
        )
        total = Feedback.query.count()

        return render_template(
            "admin_topics.html",
            topic_counts=topic_counts,
            sentiment_counts=sentiment_counts,
            priority_counts=priority_counts,
            total=total,
        )

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

