# VoC Platform — Week 1 & 2 Scaffold

Implements: Flask app skeleton, SQLite schema (Admin/Customer/Feedback/Department),
role-based auth with Flask-Login, password hashing, and the Home / Admin Login /
Customer Portal screens from the Figma mockups.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env            # edit SECRET_KEY
python seed_admin.py            # creates admin / Admin@123
python app.py                   # http://127.0.0.1:5000
```

## What's wired up
- `/` — Home page
- `/admin/login` — role-aware admin login (admin/manager/agent)
- `/customer/login` + `/customer/register` — customer portal (tabs)
- `/dashboard` — admin-only, placeholder until Week 6
- `/feedback/new` — customer-only, placeholder until Week 3
- `/logout`

## Next (Week 3)
Replace `feedback_stub.html` with the real feedback form (mockup #4),
wire it to the `Feedback` model already defined in `models.py`.
