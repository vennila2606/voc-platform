"""
Run once to create a default admin login for local testing:
    python seed_admin.py
"""
from app import create_app
from models import db, Admin

app = create_app()

with app.app_context():
    if not Admin.query.filter_by(username="admin").first():
        admin = Admin(
            username="admin",
            email="admin@vocplatform.com",
            role="admin",
            department="Operations",
        )
        admin.set_password("Admin@123")  # change immediately after first login
        db.session.add(admin)
        db.session.commit()
        print("Created default admin -> username: admin | password: Admin@123")
    else:
        print("Admin already exists, skipping.")
