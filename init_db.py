"""
Database initialisation script – Group 36 prototype.
Run with: python init_db.py
Drops and recreates all tables with updated schemas and richer seed data.
"""

import sqlite3
import os
from datetime import datetime, timedelta

DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')


def init_db():
    if os.path.exists(DATABASE):
        os.remove(DATABASE)

    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")

    # ── USERS ─────────────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE users (
            user_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            email    TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name     TEXT NOT NULL,
            role     TEXT NOT NULL CHECK(role IN (
                'student','sst_admin','its_staff','lab_technician','module_organiser'
            ))
        )
    """)

    # ── TEAMS ─────────────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE teams (
            team_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            team_type TEXT NOT NULL
        )
    """)

    # ── CATEGORIES ────────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE categories (
            category_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            default_team_id INTEGER,
            FOREIGN KEY (default_team_id) REFERENCES teams(team_id)
        )
    """)

    # ── MODULES ───────────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE modules (
            module_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            module_code  TEXT NOT NULL,
            title        TEXT NOT NULL,
            organiser_id INTEGER,
            FOREIGN KEY (organiser_id) REFERENCES users(user_id)
        )
    """)

    # ── ENROLLMENTS (student ↔ module) ────────────────────────────────────
    db.execute("""
        CREATE TABLE enrollments (
            enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    INTEGER NOT NULL,
            module_id     INTEGER NOT NULL,
            FOREIGN KEY (student_id) REFERENCES users(user_id),
            FOREIGN KEY (module_id)  REFERENCES modules(module_id)
        )
    """)

    # ── ASSESSMENTS ───────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE assessments (
            assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id     INTEGER NOT NULL,
            name          TEXT NOT NULL,
            due_date      TEXT,
            FOREIGN KEY (module_id) REFERENCES modules(module_id)
        )
    """)

    # ── SUPPORT TICKETS ───────────────────────────────────────────────────
    # status: Open (was New) | In Progress | Resolved | Closed | Withdrawn
    db.execute("""
        CREATE TABLE support_tickets (
            ticket_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id  INTEGER NOT NULL,
            category_id INTEGER,
            title       TEXT NOT NULL,
            description TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'Open'
                CHECK(status IN ('Open','In Progress','Resolved','Closed','Withdrawn')),
            resolution  TEXT,
            resolved_at TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (creator_id)  REFERENCES users(user_id),
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        )
    """)

    # ── EC APPLICATIONS ───────────────────────────────────────────────────
    # status: Submitted | Under Review | Approved | Rejected |
    #         More Evidence Needed | On Hold | Withdrawn
    # is_draft: 1 = saved draft, not yet formally submitted
    db.execute("""
        CREATE TABLE ec_applications (
            ec_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id     INTEGER NOT NULL,
            module_id      INTEGER NOT NULL,
            assessment_id  INTEGER,
            year_group     TEXT,
            reason         TEXT NOT NULL,
            description    TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'Submitted'
                CHECK(status IN (
                    'Submitted','Under Review','Approved','Rejected',
                    'More Evidence Needed','On Hold','Withdrawn'
                )),
            is_draft       INTEGER NOT NULL DEFAULT 0,
            decision_notes TEXT,
            decision_date  TEXT,
            created_at     TEXT NOT NULL,
            FOREIGN KEY (student_id)   REFERENCES users(user_id),
            FOREIGN KEY (module_id)    REFERENCES modules(module_id),
            FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id)
        )
    """)

    # ── ASSIGNMENTS ───────────────────────────────────────────────────────
    # Now supports optional individual staff assignment alongside team
    db.execute("""
        CREATE TABLE assignments (
            assignment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id          INTEGER NOT NULL,
            case_type        TEXT NOT NULL CHECK(case_type IN ('ticket','ec')),
            team_id          INTEGER,
            assigned_user_id INTEGER,
            assigned_at      TEXT NOT NULL,
            unassigned_at    TEXT,
            FOREIGN KEY (team_id)          REFERENCES teams(team_id),
            FOREIGN KEY (assigned_user_id) REFERENCES users(user_id)
        )
    """)

    # ── COMMENTS ──────────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE comments (
            comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id    INTEGER NOT NULL,
            case_type  TEXT NOT NULL CHECK(case_type IN ('ticket','ec')),
            author_id  INTEGER NOT NULL,
            content    TEXT NOT NULL,
            visibility TEXT NOT NULL DEFAULT 'public'
                CHECK(visibility IN ('public','internal')),
            created_at TEXT NOT NULL,
            FOREIGN KEY (author_id) REFERENCES users(user_id)
        )
    """)

    # ── ATTACHMENTS ───────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE attachments (
            attachment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id       INTEGER NOT NULL,
            case_type     TEXT NOT NULL CHECK(case_type IN ('ticket','ec')),
            file_name     TEXT NOT NULL,
            file_path     TEXT NOT NULL,
            uploaded_at   TEXT NOT NULL
        )
    """)

    # ── STATUS CHANGES ────────────────────────────────────────────────────
    # notes: optional reason/comment recorded alongside the status change
    db.execute("""
        CREATE TABLE status_changes (
            change_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id    INTEGER NOT NULL,
            case_type  TEXT NOT NULL CHECK(case_type IN ('ticket','ec')),
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by INTEGER NOT NULL,
            notes      TEXT,
            changed_at TEXT NOT NULL,
            FOREIGN KEY (changed_by) REFERENCES users(user_id)
        )
    """)

    # ── SERVICE STATUS ────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE service_status (
            service_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'operational'
                CHECK(status IN ('operational','degraded','outage','maintenance')),
            last_updated TEXT NOT NULL
        )
    """)

    # ══════════════════════════════════════════════════════════════════════
    # SEED DATA
    # ══════════════════════════════════════════════════════════════════════

    now = datetime.now()

    # ── Teams ─────────────────────────────────────────────────────────────
    db.execute("INSERT INTO teams VALUES (1,'Student Support Team','SST')")
    db.execute("INSERT INTO teams VALUES (2,'EECS IT Services','ITS')")
    db.execute("INSERT INTO teams VALUES (3,'EE Lab Technicians','LAB')")

    # ── Categories ────────────────────────────────────────────────────────
    db.execute("INSERT INTO categories VALUES (1,'ITL Issue',2)")
    db.execute("INSERT INTO categories VALUES (2,'EE Lab Issue',3)")
    db.execute("INSERT INTO categories VALUES (3,'Submission Issue',1)")
    db.execute("INSERT INTO categories VALUES (4,'Access Issue',2)")
    db.execute("INSERT INTO categories VALUES (5,'Service Availability',1)")
    db.execute("INSERT INTO categories VALUES (6,'General Enquiry',1)")

    # ── Users ─────────────────────────────────────────────────────────────
    # Admins / Staff
    db.execute("INSERT INTO users VALUES (1,'sst@qmul.ac.uk','password','Sarah Williams','sst_admin')")
    db.execute("INSERT INTO users VALUES (2,'its@qmul.ac.uk','password','James Chen','its_staff')")
    db.execute("INSERT INTO users VALUES (3,'its2@qmul.ac.uk','password','Olivia Harris','its_staff')")
    db.execute("INSERT INTO users VALUES (4,'lab@qmul.ac.uk','password','Maria Garcia','lab_technician')")
    db.execute("INSERT INTO users VALUES (5,'lab2@qmul.ac.uk','password','Tom Wright','lab_technician')")
    db.execute("INSERT INTO users VALUES (6,'organiser@qmul.ac.uk','password','Dr. David Brown','module_organiser')")
    db.execute("INSERT INTO users VALUES (7,'organiser2@qmul.ac.uk','password','Dr. Aisha Khan','module_organiser')")

    # Students
    db.execute("INSERT INTO users VALUES (8,'student@qmul.ac.uk','password','Alex Johnson','student')")
    db.execute("INSERT INTO users VALUES (9,'student2@qmul.ac.uk','password','Priya Patel','student')")
    db.execute("INSERT INTO users VALUES (10,'student3@qmul.ac.uk','password','Omar Farooq','student')")
    db.execute("INSERT INTO users VALUES (11,'student4@qmul.ac.uk','password','Chloe Davies','student')")
    db.execute("INSERT INTO users VALUES (12,'student5@qmul.ac.uk','password','Liam Murphy','student')")

    # ── Modules (organiser_id updated to new user IDs) ────────────────────
    db.execute("INSERT INTO modules VALUES (1,'ECS506U','Software Engineering',6)")
    db.execute("INSERT INTO modules VALUES (2,'ECS414U','Operating Systems',6)")
    db.execute("INSERT INTO modules VALUES (3,'ECS522U','Graphical User Interfaces',7)")
    db.execute("INSERT INTO modules VALUES (4,'ECS518U','Embedded Systems',7)")
    db.execute("INSERT INTO modules VALUES (5,'ECS401U','Professional Practice',6)")
    db.execute("INSERT INTO modules VALUES (6,'ECS511U','Networks',7)")

    # ── Enrollments ───────────────────────────────────────────────────────
    # Alex (8): Software Eng, Operating Systems, Professional Practice
    db.execute("INSERT INTO enrollments VALUES (1,8,1)")
    db.execute("INSERT INTO enrollments VALUES (2,8,2)")
    db.execute("INSERT INTO enrollments VALUES (3,8,5)")
    # Priya (9): GUI, Embedded Systems, Networks
    db.execute("INSERT INTO enrollments VALUES (4,9,3)")
    db.execute("INSERT INTO enrollments VALUES (5,9,4)")
    db.execute("INSERT INTO enrollments VALUES (6,9,6)")
    # Omar (10): Software Eng, GUI, Networks
    db.execute("INSERT INTO enrollments VALUES (7,10,1)")
    db.execute("INSERT INTO enrollments VALUES (8,10,3)")
    db.execute("INSERT INTO enrollments VALUES (9,10,6)")
    # Chloe (11): Operating Systems, Embedded Systems
    db.execute("INSERT INTO enrollments VALUES (10,11,2)")
    db.execute("INSERT INTO enrollments VALUES (11,11,4)")
    # Liam (12): Software Eng, Operating Systems, GUI, Embedded Systems
    db.execute("INSERT INTO enrollments VALUES (12,12,1)")
    db.execute("INSERT INTO enrollments VALUES (13,12,2)")
    db.execute("INSERT INTO enrollments VALUES (14,12,3)")
    db.execute("INSERT INTO enrollments VALUES (15,12,4)")

    # ── Assessments ───────────────────────────────────────────────────────
    db.execute("INSERT INTO assessments VALUES (1,1,'Group Project','2026-04-15')")
    db.execute("INSERT INTO assessments VALUES (2,1,'Final Exam','2026-05-20')")
    db.execute("INSERT INTO assessments VALUES (3,2,'Coursework 1','2026-03-01')")
    db.execute("INSERT INTO assessments VALUES (4,2,'Final Exam','2026-05-18')")
    db.execute("INSERT INTO assessments VALUES (5,3,'Coursework 1','2026-03-15')")
    db.execute("INSERT INTO assessments VALUES (6,3,'Final Exam','2026-05-22')")
    db.execute("INSERT INTO assessments VALUES (7,4,'Lab Report','2026-04-01')")
    db.execute("INSERT INTO assessments VALUES (8,4,'Final Exam','2026-05-25')")
    db.execute("INSERT INTO assessments VALUES (9,5,'Portfolio','2026-04-30')")
    db.execute("INSERT INTO assessments VALUES (10,6,'Network Design Report','2026-04-10')")

    # ── Service Status ────────────────────────────────────────────────────
    ts = now.isoformat()
    db.execute(f"INSERT INTO service_status VALUES (1,'Student Portal','operational','{ts}')")
    db.execute(f"INSERT INTO service_status VALUES (2,'QMplus (Moodle)','operational','{ts}')")
    db.execute(f"INSERT INTO service_status VALUES (3,'ITL Labs','operational','{ts}')")
    db.execute(f"INSERT INTO service_status VALUES (4,'EE Lab Equipment','operational','{ts}')")
    db.execute(f"INSERT INTO service_status VALUES (5,'Submission System','operational','{ts}')")

    # ── Sample Tickets ────────────────────────────────────────────────────
    def days_ago(n):
        return (now - timedelta(days=n)).isoformat()

    # ticket 1 – Open
    db.execute("""INSERT INTO support_tickets VALUES
        (1,8,1,'Workstation not booting in ITL lab B','The workstation at row 3 seat 7 will not boot past BIOS.',
         'Open',NULL,NULL,?)""",(days_ago(5),))
    db.execute("INSERT INTO assignments VALUES (1,1,'ticket',2,NULL,?,NULL)",(days_ago(5),))
    db.execute("INSERT INTO status_changes VALUES (1,1,'ticket',NULL,'Open',8,NULL,?)",(days_ago(5),))

    # ticket 2 – In Progress
    db.execute("""INSERT INTO support_tickets VALUES
        (2,9,2,'Oscilloscope faulty in EE Lab','Channel 2 on oscilloscope BK-7 shows no signal.',
         'In Progress',NULL,NULL,?)""",(days_ago(10),))
    db.execute("INSERT INTO assignments VALUES (2,2,'ticket',3,4,?,NULL)",(days_ago(10),))
    db.execute("INSERT INTO status_changes VALUES (2,2,'ticket',NULL,'Open',9,NULL,?)",(days_ago(10),))
    db.execute("INSERT INTO status_changes VALUES (3,2,'ticket','Open','In Progress',4,'Investigating the oscilloscope.',?)",(days_ago(8),))

    # ticket 3 – Resolved
    db.execute("""INSERT INTO support_tickets VALUES
        (3,10,3,'Cannot submit coursework on QMplus','The submission portal returns a 500 error when I upload my PDF.',
         'Resolved','Server-side upload limit increased to 50 MB.',?,?)""",(days_ago(1), days_ago(3)))
    db.execute("INSERT INTO assignments VALUES (3,3,'ticket',1,1,?,NULL)",(days_ago(4),))
    db.execute("INSERT INTO status_changes VALUES (4,3,'ticket',NULL,'Open',10,NULL,?)",(days_ago(4),))
    db.execute("INSERT INTO status_changes VALUES (5,3,'ticket','Open','In Progress',1,NULL,?)",(days_ago(3),))
    db.execute("INSERT INTO status_changes VALUES (6,3,'ticket','In Progress','Resolved',1,'Upload limit increased.',?)",(days_ago(1),))

    # ticket 4 – Withdrawn by student
    db.execute("""INSERT INTO support_tickets VALUES
        (4,11,6,'Query about deadline extension','Is it possible to get a 48h extension on the networks report?',
         'Withdrawn',NULL,NULL,?)""",(days_ago(7),))
    db.execute("INSERT INTO assignments VALUES (4,4,'ticket',1,NULL,?,NULL)",(days_ago(7),))
    db.execute("INSERT INTO status_changes VALUES (7,4,'ticket',NULL,'Open',11,NULL,?)",(days_ago(7),))
    db.execute("INSERT INTO status_changes VALUES (8,4,'ticket','Open','Withdrawn',11,'Student withdrew the request.',?)",(days_ago(5),))

    # ticket 5 – Open (Alex, ITS)
    db.execute("""INSERT INTO support_tickets VALUES
        (5,8,1,'Cannot log in to lab machines','My QMUL credentials are rejected on every ITL machine I try.',
         'Open',NULL,NULL,?)""",(days_ago(2),))
    db.execute("INSERT INTO assignments VALUES (5,5,'ticket',2,NULL,?,NULL)",(days_ago(2),))
    db.execute("INSERT INTO status_changes VALUES (9,5,'ticket',NULL,'Open',8,NULL,?)",(days_ago(2),))

    # ── Sample EC Applications ────────────────────────────────────────────
    # EC 1 – Approved (Alex)
    db.execute("""INSERT INTO ec_applications VALUES
        (1,8,1,1,'Year 2','Medical','I was hospitalised for three days prior to the submission deadline.',
         'Approved',0,'Extension of 5 days granted.',?,?)""",(days_ago(1), days_ago(12)))
    db.execute("INSERT INTO assignments VALUES (6,1,'ec',1,NULL,?,NULL)",(days_ago(12),))
    db.execute("INSERT INTO status_changes VALUES (10,1,'ec',NULL,'Submitted',8,NULL,?)",(days_ago(12),))
    db.execute("INSERT INTO status_changes VALUES (11,1,'ec','Submitted','Under Review',1,NULL,?)",(days_ago(10),))
    db.execute("INSERT INTO status_changes VALUES (12,1,'ec','Under Review','Approved',1,'Extension of 5 days granted.',?)",(days_ago(1),))

    # EC 2 – Under Review (Priya)
    db.execute("""INSERT INTO ec_applications VALUES
        (2,9,3,5,'Year 2','Personal','Family emergency on the day of the assessment.',
         'Under Review',0,NULL,NULL,?)""",(days_ago(6),))
    db.execute("INSERT INTO assignments VALUES (7,2,'ec',1,NULL,?,NULL)",(days_ago(6),))
    db.execute("INSERT INTO status_changes VALUES (13,2,'ec',NULL,'Submitted',9,NULL,?)",(days_ago(6),))
    db.execute("INSERT INTO status_changes VALUES (14,2,'ec','Submitted','Under Review',1,NULL,?)",(days_ago(4),))

    # EC 3 – More Evidence Needed (Omar)
    db.execute("""INSERT INTO ec_applications VALUES
        (3,10,1,2,'Year 3','Mental Health','Severe anxiety prevented me from completing the exam.',
         'More Evidence Needed',0,'Please upload a letter from your GP or counsellor.',NULL,?)""",(days_ago(9),))
    db.execute("INSERT INTO assignments VALUES (8,3,'ec',1,NULL,?,NULL)",(days_ago(9),))
    db.execute("INSERT INTO status_changes VALUES (15,3,'ec',NULL,'Submitted',10,NULL,?)",(days_ago(9),))
    db.execute("INSERT INTO status_changes VALUES (16,3,'ec','Submitted','More Evidence Needed',1,'GP letter required.',?)",(days_ago(5),))

    # EC 4 – On Hold (Chloe)
    db.execute("""INSERT INTO ec_applications VALUES
        (4,11,4,7,'Year 1','Bereavement','My grandmother passed away the week of the lab report.',
         'On Hold',0,'Awaiting confirmation of relationship from registry.',NULL,?)""",(days_ago(14),))
    db.execute("INSERT INTO assignments VALUES (9,4,'ec',1,NULL,?,NULL)",(days_ago(14),))
    db.execute("INSERT INTO status_changes VALUES (17,4,'ec',NULL,'Submitted',11,NULL,?)",(days_ago(14),))
    db.execute("INSERT INTO status_changes VALUES (18,4,'ec','Submitted','On Hold',1,'Awaiting registry confirmation.',?)",(days_ago(8),))

    # EC 5 – Draft (Liam – not yet submitted)
    db.execute("""INSERT INTO ec_applications VALUES
        (5,12,2,3,'Year 2','Medical','I had a severe migraine during the coursework week.',
         'Submitted',1,NULL,NULL,?)""",(days_ago(1),))

    # EC 6 – Rejected (Priya)
    db.execute("""INSERT INTO ec_applications VALUES
        (6,9,4,8,'Year 2','Other','Forgot to prepare in time.',
         'Rejected',0,'Insufficient grounds for EC under university policy.',?,?)""",(days_ago(3), days_ago(20)))
    db.execute("INSERT INTO assignments VALUES (10,6,'ec',1,NULL,?,NULL)",(days_ago(20),))
    db.execute("INSERT INTO status_changes VALUES (19,6,'ec',NULL,'Submitted',9,NULL,?)",(days_ago(20),))
    db.execute("INSERT INTO status_changes VALUES (20,6,'ec','Submitted','Rejected',1,'Insufficient grounds.',?)",(days_ago(3),))

    # ── Comments ──────────────────────────────────────────────────────────
    db.execute(f"""INSERT INTO comments VALUES
        (1,2,'ticket',4,'I have checked the oscilloscope and ordered a replacement probe.','public','{days_ago(7)}')""")
    db.execute(f"""INSERT INTO comments VALUES
        (2,1,'ec',1,'We have received your application and will review it shortly.','public','{days_ago(11)}')""")
    db.execute(f"""INSERT INTO comments VALUES
        (3,3,'ec',1,'Please note: only a letter from your registered GP will be accepted.','public','{days_ago(5)}')""")

    db.commit()
    db.close()
    print("Database initialised successfully.")


if __name__ == '__main__':
    init_db()
