# QMUL Issues & Feedback System — Group 36 Prototype

ECS506U Software Engineering Group Project

## Quick Start

```bash
# 1. Install Flask (only dependency)
pip install flask

# 2. Create the database with test data
python setup_db.py

# 3. Run the app
python app.py

# 4. Open in browser
# http://127.0.0.1:5000
```

## Demo Accounts

| Role              | Email                    | Password |
|-------------------|--------------------------|----------|
| Student           | student@qmul.ac.uk      | password |
| Student 2         | student2@qmul.ac.uk     | password |
| SST Admin         | sst@qmul.ac.uk          | password |
| ITS Staff         | its@qmul.ac.uk          | password |
| Lab Technician    | lab@qmul.ac.uk          | password |
| Module Organiser  | organiser@qmul.ac.uk    | password |

## Use Cases Covered

1. **Login** — Role-based authentication and dashboard routing
2. **Submit Ticket** — Student submits support ticket with category, title, description, optional file
3. **Manage Ticket** — SST Admin / ITS / Lab Tech update status, add comments, resolve tickets
4. **Submit EC** — Student submits extenuating circumstances application
5. **Review EC** — SST Admin reviews, approves/rejects/requests more evidence
6. **Generate EC Report** — SST Admin views ticket and EC statistics

## Project Structure

```
qmul-prototype/
├── app.py                    # Main Flask application (all routes)
├── setup_db.py               # Database schema + seed data
├── database.db               # SQLite database (created by setup_db.py)
├── requirements.txt
├── README.md
├── static/
│   ├── css/
│   │   └── style.css         # Custom styles + status badges
│   ├── js/                   # (add any JS here)
│   └── uploads/              # Uploaded evidence files
└── templates/
    ├── base.html             # Shared layout (navbar, Bootstrap, flash messages)
    ├── login.html            # Login page
    ├── student/
    │   ├── dashboard.html    # Student home: my tickets + my ECs
    │   ├── submit_ticket.html
    │   ├── submit_ec.html
    │   ├── view_ticket.html  # Ticket detail + status timeline
    │   └── view_ec.html      # EC detail + decision + timeline
    ├── sst/
    │   ├── dashboard.html    # All tickets + ECs with filters
    │   ├── manage_ticket.html # Update status, comment, reassign
    │   ├── review_ec.html    # Approve/reject/request evidence
    │   └── reports.html      # Ticket + EC statistics
    ├── its/
    │   ├── dashboard.html    # ITL tickets only
    │   └── manage_ticket.html
    ├── lab/
    │   ├── dashboard.html    # EE Lab tickets only
    │   └── manage_ticket.html
    └── organiser/
        └── dashboard.html    # Read-only EC outcomes
```

## Who Works on What

| Role | Owner | Files |
|------|-------|-------|
| 1. Prototype Lead / Integrator | — | `app.py` structure, `base.html`, `style.css`, integration |
| 2. Auth + Navigation | — | `login.html`, auth routes in `app.py`, `setup_db.py`, navbar in `base.html` |
| 3. Student Use-Cases | — | Everything in `templates/student/`, student routes in `app.py` |
| 4. SST/Admin Workflows | — | Everything in `templates/sst/`, SST routes in `app.py` |
| 5. ITS + Lab Tech Workflows | — | `templates/its/`, `templates/lab/`, `templates/organiser/`, staff routes in `app.py` |
| 6. Acceptance Test Lead | - | Acceptance test document (separate Word doc) |
| 7. Presentation + QA Lead | — | Demo script, rehearsals, QA testing |

## Resetting the Database

If you need a fresh database (e.g. after testing), just run:

```bash
python setup_db.py
```

This drops all tables, recreates them, and re-inserts the seed data.

## Tech Stack

- **Backend:** Flask (Python)
- **Frontend:** Jinja2 templates + Bootstrap 5 + Bootstrap Icons
- **Database:** SQLite
- **No build step required** — just `pip install flask` and run
