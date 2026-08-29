"""
Analytics / Aggregation Service.

All Chart.js data, KPIs, and filters are computed here from SQLite via
SQLAlchemy — nothing is hard-coded (item 8/17). This module is also what
builds the compact aggregated-stats text sent to Gemini for the Smart
Recommendation Engine (item 7) and Weekly Summary (item 13) — raw review
text is never sent in bulk, only counts/percentages (item 15 efficiency rule).
"""
from datetime import datetime, timedelta
from sqlalchemy import func

from models import db, Feedback


def apply_filters(query, args):
    """Item 11: shared filter logic used by every dashboard data route.
    args is a dict-like (request.args) with optional keys:
    date_from, date_to, category, product, sentiment, priority, department."""
    if args.get("date_from"):
        query = query.filter(Feedback.created_at >= args["date_from"])
    if args.get("date_to"):
        # inclusive of the whole end day
        end = datetime.strptime(args["date_to"], "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Feedback.created_at < end)
    if args.get("category"):
        query = query.filter(Feedback.category == args["category"])
    if args.get("product"):
        query = query.filter(Feedback.product_service == args["product"])
    if args.get("sentiment"):
        query = query.filter(Feedback.sentiment == args["sentiment"])
    if args.get("priority"):
        query = query.filter(Feedback.priority == args["priority"])
    if args.get("department"):
        query = query.filter(Feedback.suggested_department == args["department"])
    return query


def calculate_voice_health_score(feedback_rows):
    """
    Item 17: Voice Health Score — documented weighted formula, 0-100.

    Components (each normalized to a 0-1 scale before weighting):
      1. Sentiment score   (35%) — (positive - negative) / total, rescaled 0-1
      2. Average rating    (25%) — average star rating / 5
      3. Resolution rate   (20%) — resolved reviews / total
      4. Review quality    (10%) — average quality_score / 100
      5. Engagement        (10%) — proportion of reviews with substantive
                                    review text (>=10 words), as a simple
                                    proxy for customer engagement depth

    VHS = 100 * (0.35*sentiment + 0.25*rating + 0.20*resolution
                 + 0.10*quality + 0.10*engagement)

    Never random — always derived from the rows passed in. Returns None
    if there's no data to compute from (rather than a fake default).
    """
    rows = [f for f in feedback_rows]
    total = len(rows)
    if total == 0:
        return None

    positive = sum(1 for f in rows if f.sentiment == "Positive")
    negative = sum(1 for f in rows if f.sentiment == "Negative")
    sentiment_component = ((positive - negative) / total + 1) / 2  # rescale -1..1 -> 0..1

    ratings = [f.rating for f in rows if f.rating is not None]
    rating_component = (sum(ratings) / len(ratings) / 5) if ratings else 0.5

    resolved = sum(1 for f in rows if f.status == "Resolved")
    resolution_component = resolved / total

    quality_scores = [f.quality_score for f in rows if f.quality_score is not None]
    quality_component = (sum(quality_scores) / len(quality_scores) / 100) if quality_scores else 0.5

    engaged = sum(1 for f in rows if f.review_text and len(f.review_text.split()) >= 10)
    engagement_component = engaged / total

    score = 100 * (
        0.35 * sentiment_component
        + 0.25 * rating_component
        + 0.20 * resolution_component
        + 0.10 * quality_component
        + 0.10 * engagement_component
    )
    return round(max(0, min(100, score)), 1)


def get_voice_health_score_with_trend(args):
    """Item 17: current-period VHS plus comparison against the immediately
    preceding period of equal length — shows Improving / Stable / Declining."""
    current_rows = apply_filters(Feedback.query, args).all()
    current_score = calculate_voice_health_score(current_rows)

    # Determine the equivalent "previous period" window
    date_from = args.get("date_from")
    date_to = args.get("date_to")
    if date_from:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d") if date_to else datetime.utcnow()
        period_length = end - start
        prev_end = start
        prev_start = start - period_length
    else:
        # Default: compare last 7 days against the 7 days before that
        prev_end = datetime.utcnow() - timedelta(days=7)
        prev_start = prev_end - timedelta(days=7)

    prev_rows = Feedback.query.filter(
        Feedback.created_at >= prev_start, Feedback.created_at < prev_end
    ).all()
    previous_score = calculate_voice_health_score(prev_rows)

    if current_score is None:
        trend = "→ No data"
    elif previous_score is None:
        trend = "→ No prior data to compare"
    elif current_score > previous_score + 1:
        trend = "↑ Improving"
    elif current_score < previous_score - 1:
        trend = "↓ Declining"
    else:
        trend = "→ Stable"

    return {"score": current_score, "previous_score": previous_score, "trend": trend}


def get_kpis(args):
    """Item 9: dashboard KPI numbers."""
    base = apply_filters(Feedback.query, args)
    total = base.count()

    if total == 0:
        return {
            "total_feedback": 0, "positive_pct": 0, "negative_pct": 0,
            "neutral_mixed_pct": 0, "average_rating": None,
            "high_priority_count": 0, "authenticity_rate": None,
            "voice_health_score": None,
        }

    positive = apply_filters(Feedback.query, args).filter(Feedback.sentiment == "Positive").count()
    negative = apply_filters(Feedback.query, args).filter(Feedback.sentiment == "Negative").count()
    neutral_mixed = total - positive - negative

    ratings = [f.rating for f in base.all() if f.rating is not None]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    high_priority = apply_filters(Feedback.query, args).filter(
        Feedback.priority.in_(["High", "Critical"])
    ).count()

    authentic = apply_filters(Feedback.query, args).filter(Feedback.is_authentic == True).count()
    authenticity_rate = round((authentic / total) * 100, 1) if total else None

    voice_health_score = calculate_voice_health_score(base.all())

    return {
        "total_feedback": total,
        "positive_pct": round((positive / total) * 100, 1),
        "negative_pct": round((negative / total) * 100, 1),
        "neutral_mixed_pct": round((neutral_mixed / total) * 100, 1),
        "average_rating": round(avg_rating, 1) if avg_rating else None,
        "high_priority_count": high_priority,
        "authenticity_rate": authenticity_rate,
        "voice_health_score": voice_health_score,
    }


def get_sentiment_distribution(args):
    """Item 10A: doughnut chart data."""
    rows = apply_filters(Feedback.query, args).all()
    counts = {}
    for r in rows:
        key = r.sentiment or "Unclassified"
        counts[key] = counts.get(key, 0) + 1
    return counts


def get_feedback_trend(args, granularity="daily"):
    """Item 10B: line chart — feedback volume over time."""
    base = apply_filters(Feedback.query, args).all()
    buckets = {}
    for fb in base:
        if not fb.created_at:
            continue
        if granularity == "monthly":
            key = fb.created_at.strftime("%Y-%m")
        elif granularity == "weekly":
            key = fb.created_at.strftime("%Y-W%W")
        else:
            key = fb.created_at.strftime("%Y-%m-%d")
        buckets[key] = buckets.get(key, 0) + 1
    return dict(sorted(buckets.items()))


def get_sentiment_trend(args, granularity="daily"):
    """Item 10C: line chart — sentiment over time."""
    base = apply_filters(Feedback.query, args).all()
    buckets = {}
    for fb in base:
        if not fb.created_at:
            continue
        if granularity == "monthly":
            key = fb.created_at.strftime("%Y-%m")
        elif granularity == "weekly":
            key = fb.created_at.strftime("%Y-W%W")
        else:
            key = fb.created_at.strftime("%Y-%m-%d")
        buckets.setdefault(key, {"Positive": 0, "Negative": 0, "Neutral": 0, "Mixed": 0})
        s = fb.sentiment or "Neutral"
        if s in buckets[key]:
            buckets[key][s] += 1
    return dict(sorted(buckets.items()))


def get_category_distribution(args):
    """Item 10D: bar chart — complaint category counts."""
    rows = apply_filters(Feedback.query, args).all()
    counts = {}
    for r in rows:
        key = r.category or "Unclassified"
        counts[key] = counts.get(key, 0) + 1
    return counts


def get_priority_distribution(args):
    """Item 10E: priority counts."""
    rows = apply_filters(Feedback.query, args).all()
    counts = {}
    for r in rows:
        key = r.priority or "Unclassified"
        counts[key] = counts.get(key, 0) + 1
    return counts


def get_department_distribution(args):
    """Item 10F: department-wise issue counts."""
    rows = apply_filters(Feedback.query, args).all()
    counts = {}
    for r in rows:
        key = r.suggested_department or "Unassigned"
        counts[key] = counts.get(key, 0) + 1
    return counts


def get_filter_options():
    """Populates the filter dropdowns from real distinct DB values (item 11)."""
    categories = [r[0] for r in db.session.query(Feedback.category).distinct() if r[0]]
    products = [r[0] for r in db.session.query(Feedback.product_service).distinct() if r[0]]
    sentiments = [r[0] for r in db.session.query(Feedback.sentiment).distinct() if r[0]]
    priorities = [r[0] for r in db.session.query(Feedback.priority).distinct() if r[0]]
    departments = [r[0] for r in db.session.query(Feedback.suggested_department).distinct() if r[0]]
    return {
        "categories": sorted(categories),
        "products": sorted(products),
        "sentiments": sorted(sentiments),
        "priorities": sorted(priorities),
        "departments": sorted(departments),
    }


def get_smart_insights(args, limit_days=7):
    """
    Item 12: rule-based (not Gemini — cheap, instant, no API cost) insights
    generated purely from real aggregated data, e.g. week-over-week deltas.
    """
    insights = []
    now = datetime.utcnow()
    this_week_start = now - timedelta(days=limit_days)
    last_week_start = now - timedelta(days=limit_days * 2)

    this_week = Feedback.query.filter(Feedback.created_at >= this_week_start).all()
    last_week = Feedback.query.filter(
        Feedback.created_at >= last_week_start, Feedback.created_at < this_week_start
    ).all()

    # Category trend deltas
    def _count_by(rows, field):
        counts = {}
        for r in rows:
            key = getattr(r, field)
            if key:
                counts[key] = counts.get(key, 0) + 1
        return counts

    this_cat = _count_by(this_week, "category")
    last_cat = _count_by(last_week, "category")
    for cat, count in this_cat.items():
        prev = last_cat.get(cat, 0)
        if prev > 0 and count > prev:
            pct_increase = round(((count - prev) / prev) * 100)
            if pct_increase >= 20:
                insights.append(f"{cat} complaints increased by {pct_increase}% this week.")
        elif prev == 0 and count >= 3:
            insights.append(f"{cat} is a newly emerging complaint category this week ({count} reports).")

    # Department with highest negative sentiment share
    dept_negative = {}
    dept_total = {}
    for r in this_week:
        dept = r.suggested_department or "Unassigned"
        dept_total[dept] = dept_total.get(dept, 0) + 1
        if r.sentiment == "Negative":
            dept_negative[dept] = dept_negative.get(dept, 0) + 1
    if dept_total:
        worst_dept = max(
            dept_total, key=lambda d: (dept_negative.get(d, 0) / dept_total[d])
        )
        if dept_total[worst_dept] >= 3 and dept_negative.get(worst_dept, 0) > 0:
            insights.append(f"{worst_dept} has the highest negative sentiment share this week.")

    # Silent Customer Detector — product with feedback but disproportionately low volume vs others
    product_counts = _count_by(this_week, "product_service")
    if len(product_counts) >= 2:
        avg_count = sum(product_counts.values()) / len(product_counts)
        for product, count in product_counts.items():
            if count < avg_count * 0.3:
                insights.append(f"{product} has unusually low feedback volume compared to other products.")

    if not insights:
        insights.append("No significant changes detected in the selected period.")

    return insights


def build_aggregated_stats_text(args=None):
    """
    Builds a compact text summary of current stats — this is what gets
    sent to Gemini for the Recommendation Engine (item 7), NOT raw reviews
    (item 15 efficiency rule).
    """
    args = args or {}
    kpis = get_kpis(args)
    categories = get_category_distribution(args)
    priorities = get_priority_distribution(args)
    departments = get_department_distribution(args)

    lines = [
        f"Total feedback: {kpis['total_feedback']}",
        f"Positive: {kpis['positive_pct']}%, Negative: {kpis['negative_pct']}%, Neutral/Mixed: {kpis['neutral_mixed_pct']}%",
        f"Average rating: {kpis['average_rating']}",
        "Complaints by category: " + ", ".join(f"{k}: {v}" for k, v in categories.items()),
        "Priority breakdown: " + ", ".join(f"{k}: {v}" for k, v in priorities.items()),
        "Department-wise issues: " + ", ".join(f"{k}: {v}" for k, v in departments.items()),
    ]
    return "\n".join(lines)


def build_weekly_stats_text():
    """Builds the compact weekly aggregated stats sent to Gemini for the
    Weekly Executive Summary (item 13) — never individual reviews."""
    week_ago = datetime.utcnow() - timedelta(days=7)
    args = {"date_from": week_ago.strftime("%Y-%m-%d")}
    kpis = get_kpis(args)
    categories = get_category_distribution(args)
    priorities = get_priority_distribution(args)
    departments = get_department_distribution(args)
    insights = get_smart_insights(args)

    lines = [
        f"Period: last 7 days",
        f"Total reviews: {kpis['total_feedback']}",
        f"Positive: {kpis['positive_pct']}%, Negative: {kpis['negative_pct']}%, Neutral/Mixed: {kpis['neutral_mixed_pct']}%",
        f"Average rating: {kpis['average_rating']}",
        f"Voice Health Score: {kpis['voice_health_score']}",
        "Top complaint categories: " + ", ".join(f"{k}: {v}" for k, v in categories.items()),
        "Priority breakdown: " + ", ".join(f"{k}: {v}" for k, v in priorities.items()),
        "Department-wise complaints: " + ", ".join(f"{k}: {v}" for k, v in departments.items()),
        "Detected trends: " + "; ".join(insights),
    ]
    return "\n".join(lines)

# ---------- Item 18: Silent Customer Detector ----------

def get_silent_customer_risks(min_sales_threshold=50):
    """
    Item 18: compares imported sales/activity volume (SalesData) against
    actual feedback row counts per product, to flag products with high
    activity but disproportionately low feedback — a "Silent Customer Risk",
    NOT a claim that low feedback means dissatisfaction (explicitly per spec).

    Returns a list of dicts: product, category, sales, reviews, feedback_rate, risk.
    Only products present in SalesData are evaluated — if no sales data has
    been imported yet, this returns an empty list (not fake results).
    """
    from models import SalesData

    sales_rows = SalesData.query.all()
    results = []

    for sale in sales_rows:
        review_count = Feedback.query.filter(
            Feedback.product_service == sale.product_name
        ).count()

        if sale.sales_count <= 0:
            continue
        feedback_rate = round((review_count / sale.sales_count) * 100, 2)

        # Risk banding — purely about feedback SCARCITY relative to volume,
        # not a claim about sentiment.
        if sale.sales_count < min_sales_threshold:
            risk = "Not enough sales volume to assess"
        elif feedback_rate < 1:
            risk = "High"
        elif feedback_rate < 3:
            risk = "Medium"
        else:
            risk = "Low"

        results.append({
            "product": sale.product_name,
            "category": sale.category,
            "sales": sale.sales_count,
            "reviews": review_count,
            "feedback_rate": feedback_rate,
            "risk": risk,
        })

    # Highest risk first
    risk_order = {"High": 0, "Medium": 1, "Low": 2, "Not enough sales volume to assess": 3}
    results.sort(key=lambda r: risk_order.get(r["risk"], 4))
    return results


# ---------- Item 19: Emerging Issue Radar ----------

def get_emerging_issues(period_days=7, min_previous_count=3, min_increase_pct=20):
    """
    Item 19: compares issue (topic) frequency between the current period
    and the immediately preceding period of equal length, flagging issues
    whose frequency increased sharply.

    Returns a list of dicts: issue, category, previous_count, current_count,
    percentage_increase, severity, trend — sorted by percentage increase.
    """
    now = datetime.utcnow()
    current_start = now - timedelta(days=period_days)
    previous_start = current_start - timedelta(days=period_days)

    current_rows = Feedback.query.filter(Feedback.created_at >= current_start).all()
    previous_rows = Feedback.query.filter(
        Feedback.created_at >= previous_start, Feedback.created_at < current_start
    ).all()

    def _count_by_issue(rows):
        counts = {}
        cat_for_issue = {}
        for r in rows:
            issue = r.topic or "Unclassified"
            counts[issue] = counts.get(issue, 0) + 1
            cat_for_issue[issue] = r.category
        return counts, cat_for_issue

    current_counts, current_cats = _count_by_issue(current_rows)
    previous_counts, _ = _count_by_issue(previous_rows)

    emerging = []
    for issue, current_count in current_counts.items():
        previous_count = previous_counts.get(issue, 0)

        if previous_count >= min_previous_count:
            pct_increase = round(((current_count - previous_count) / previous_count) * 100)
        elif previous_count == 0 and current_count >= min_previous_count:
            pct_increase = 100  # brand new issue this period, treat as +100%
        else:
            continue  # not enough history to call this "emerging"

        if pct_increase < min_increase_pct:
            continue

        if pct_increase >= 100:
            severity = "Critical"
        elif pct_increase >= 50:
            severity = "High"
        else:
            severity = "Medium"

        emerging.append({
            "issue": issue,
            "category": current_cats.get(issue, "Unclassified"),
            "previous_count": previous_count,
            "current_count": current_count,
            "percentage_increase": pct_increase,
            "severity": severity,
            "trend": "↑ Increasing",
        })

    emerging.sort(key=lambda e: e["percentage_increase"], reverse=True)
    return emerging

# ---------- Department-wise Action Queue ----------

def get_department_action_queue(status_filter=None):
    """
    Groups open (non-Resolved) feedback into department-level action items:
    one row per (department, issue) combination, showing how many customers
    are affected, worst priority/sentiment among them, and status. This is
    what a manager actually acts on, rather than scrolling raw feedback rows.
    """
    query = Feedback.query.filter(Feedback.is_authentic == True)
    if status_filter:
        query = query.filter(Feedback.status == status_filter)
    rows = query.all()

    priority_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, None: 4}
    groups = {}

    for r in rows:
        dept = r.suggested_department or "Unassigned"
        issue = r.topic or "Unclassified"
        key = (dept, issue)
        if key not in groups:
            groups[key] = {
                "department": dept,
                "issue": issue,
                "category": r.category,
                "affected_customers": 0,
                "priority": r.priority,
                "worst_sentiment_score": r.sentiment_score if r.sentiment_score is not None else 0,
                "earliest_date": r.created_at,
                "status": r.status or "New",
                "feedback_ids": [],
            }
        g = groups[key]
        g["affected_customers"] += 1
        g["feedback_ids"].append(r.id)
        if priority_rank.get(r.priority, 4) < priority_rank.get(g["priority"], 4):
            g["priority"] = r.priority
        if r.sentiment_score is not None and r.sentiment_score < g["worst_sentiment_score"]:
            g["worst_sentiment_score"] = r.sentiment_score
        if r.created_at and (not g["earliest_date"] or r.created_at < g["earliest_date"]):
            g["earliest_date"] = r.created_at
        # Status shown is "In Progress" if ANY row in the group is in
        # progress, "Resolved" only if ALL rows are resolved — otherwise "New".
        statuses = {rr.status for rr in rows if rr.suggested_department == dept and (rr.topic or "Unclassified") == issue}
        if statuses == {"Resolved"}:
            g["status"] = "Resolved"
        elif "In Progress" in statuses:
            g["status"] = "In Progress"
        else:
            g["status"] = "Pending"

    queue = list(groups.values())
    queue.sort(key=lambda g: (priority_rank.get(g["priority"], 4), -g["affected_customers"]))
    return queue


# ---------- What-If Simulator ----------

def simulate_issue_resolution(issue_name: str, reduction_pct: int):
    """
    Estimates how the Voice Health Score would change if a given issue's
    negative feedback were reduced by reduction_pct%. This is a projection,
    not a claim — it re-runs the real VHS formula on a modified copy of the
    current data, removing a proportion of negative/critical rows tagged
    with that issue (simulating them being resolved and no longer occurring).
    """
    all_rows = Feedback.query.filter(Feedback.is_authentic == True).all()
    current_score = calculate_voice_health_score(all_rows)

    affected = [r for r in all_rows if (r.topic or "Unclassified") == issue_name]
    if not affected:
        return {
            "issue": issue_name, "current_vhs": current_score, "predicted_vhs": current_score,
            "delta": 0, "affected_count": 0, "note": "No feedback currently tagged with this issue.",
        }

    # "Resolving" a fraction of affected reviews: simulate by treating that
    # fraction as if their sentiment improved to Neutral and status became
    # Resolved, rather than deleting them (we don't invent positive reviews).
    import copy
    n_to_resolve = round(len(affected) * (reduction_pct / 100))
    # Prioritize resolving the most negative ones first — that's what
    # "resolving the issue" would actually target.
    affected_sorted = sorted(affected, key=lambda r: r.sentiment_score if r.sentiment_score is not None else 0)
    to_resolve_ids = {r.id for r in affected_sorted[:n_to_resolve]}

    class _Sim:
        """Lightweight stand-in mimicking the Feedback attributes
        calculate_voice_health_score() reads, without touching the DB."""
        def __init__(self, r, resolved):
            self.sentiment = "Neutral" if resolved else r.sentiment
            self.rating = r.rating
            self.status = "Resolved" if resolved else r.status
            self.quality_score = r.quality_score
            self.review_text = r.review_text

    simulated_rows = [_Sim(r, r.id in to_resolve_ids) for r in all_rows]
    predicted_score = calculate_voice_health_score(simulated_rows)

    return {
        "issue": issue_name,
        "current_vhs": current_score,
        "predicted_vhs": predicted_score,
        "delta": round(predicted_score - current_score, 1) if (predicted_score is not None and current_score is not None) else None,
        "affected_count": len(affected),
        "resolved_count": n_to_resolve,
        "reduction_pct": reduction_pct,
    }


def get_issue_list():
    """Distinct issue/topic values currently in the database, for the
    What-If Simulator's dropdown."""
    rows = db.session.query(Feedback.topic).distinct().all()
    return sorted([r[0] for r in rows if r[0]])

# ---------- Feedback Journey Timeline ----------

def get_customer_journey(customer_id: int):
    """
    Item: Feedback Journey Timeline — shows how a specific customer's
    sentiment changed across their reviews over time, including support
    interaction/resolution data where it actually exists (never invented).
    """
    reviews = (
        Feedback.query.filter_by(customer_id=customer_id)
        .order_by(Feedback.created_at.asc())
        .all()
    )
    timeline = []
    for r in reviews:
        timeline.append({
            "id": r.id,
            "date": r.created_at,
            "product": r.product_service,
            "category": r.category,
            "rating": r.rating,
            "review_text": r.review_text,
            "sentiment": r.sentiment,
            "issue": r.topic,
            "status": r.status,
            # Only shown if actually present — never fabricated:
            "support_interaction": getattr(r, "support_interaction", None),
            "resolution_date": getattr(r, "resolution_date", None),
        })
    return timeline


def get_customers_with_multiple_reviews(limit=20):
    """List of customers who've submitted 2+ reviews — these are the ones
    with an actual journey worth viewing (a single review has no 'change' to show)."""
    from models import Customer
    customers = Customer.query.all()
    result = []
    for c in customers:
        count = Feedback.query.filter_by(customer_id=c.id).count()
        if count >= 2:
            result.append({"id": c.id, "name": c.name, "review_count": count})
    result.sort(key=lambda x: x["review_count"], reverse=True)
    return result[:limit]


# ---------- Export ----------

def export_feedback_rows(args, fmt="csv"):
    """Exports currently-filtered feedback as CSV or JSON text. Excludes
    private contact info (item: never expose other customers' private data)
    — export is an admin-only action so this is about keeping the exported
    file itself clean/shareable, not a privacy bypass."""
    rows = apply_filters(Feedback.query, args).order_by(Feedback.created_at.desc()).all()

    records = []
    for r in rows:
        records.append({
            "id": r.id,
            "date": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            "customer_name": r.customer_name,
            "product": r.product_service,
            "category": r.category,
            "rating": r.rating,
            "review_text": r.review_text,
            "sentiment": r.sentiment,
            "sentiment_score": r.sentiment_score,
            "emotion": r.emotion,
            "intent": r.intent,
            "issue": r.topic,
            "priority": r.priority,
            "department": r.suggested_department,
            "status": r.status,
            "channel": r.channel,
        })
    return records
