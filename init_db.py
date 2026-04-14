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
                'student','sst_admin','its_staff','lab_technician','module_organiser','admin'
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
    db.execute("INSERT INTO users VALUES (1,'admin@qmul.ac.uk','password','System Admin','admin')")
    db.execute("INSERT INTO users VALUES (2,'sst@qmul.ac.uk','password','Sarah Williams','sst_admin')")
    db.execute("INSERT INTO users VALUES (3,'its@qmul.ac.uk','password','James Chen','its_staff')")
    db.execute("INSERT INTO users VALUES (4,'its2@qmul.ac.uk','password','Olivia Harris','its_staff')")
    db.execute("INSERT INTO users VALUES (5,'lab@qmul.ac.uk','password','Maria Garcia','lab_technician')")
    db.execute("INSERT INTO users VALUES (6,'lab2@qmul.ac.uk','password','Tom Wright','lab_technician')")
    db.execute("INSERT INTO users VALUES (7,'organiser@qmul.ac.uk','password','Dr. David Brown','module_organiser')")
    db.execute("INSERT INTO users VALUES (8,'organiser2@qmul.ac.uk','password','Dr. Aisha Khan','module_organiser')")
    db.execute("INSERT INTO users VALUES (9,'student@qmul.ac.uk','password','Alex Johnson','student')")
    db.execute("INSERT INTO users VALUES (10,'student2@qmul.ac.uk','password','Priya Patel','student')")
    db.execute("INSERT INTO users VALUES (11,'student3@qmul.ac.uk','password','Omar Farooq','student')")
    db.execute("INSERT INTO users VALUES (12,'student4@qmul.ac.uk','password','Chloe Davies','student')")
    db.execute("INSERT INTO users VALUES (13,'student5@qmul.ac.uk','password','Liam Murphy','student')")

    # ── Modules ────────────────────────────────────────────────────────────
    db.execute("INSERT INTO modules VALUES (1,'ECS506U','Software Engineering',7)")
    db.execute("INSERT INTO modules VALUES (2,'ECS414U','Operating Systems',7)")
    db.execute("INSERT INTO modules VALUES (3,'ECS522U','Graphical User Interfaces',8)")
    db.execute("INSERT INTO modules VALUES (4,'ECS518U','Embedded Systems',8)")
    db.execute("INSERT INTO modules VALUES (5,'ECS401U','Professional Practice',7)")
    db.execute("INSERT INTO modules VALUES (6,'ECS511U','Networks',8)")

    # ── Enrollments ───────────────────────────────────────────────────────
    db.execute("INSERT INTO enrollments VALUES (1,9,1)")
    db.execute("INSERT INTO enrollments VALUES (2,9,2)")
    db.execute("INSERT INTO enrollments VALUES (3,9,5)")
    db.execute("INSERT INTO enrollments VALUES (4,10,3)")
    db.execute("INSERT INTO enrollments VALUES (5,10,4)")
    db.execute("INSERT INTO enrollments VALUES (6,10,6)")
    db.execute("INSERT INTO enrollments VALUES (7,11,1)")
    db.execute("INSERT INTO enrollments VALUES (8,11,3)")
    db.execute("INSERT INTO enrollments VALUES (9,11,6)")
    db.execute("INSERT INTO enrollments VALUES (10,12,2)")
    db.execute("INSERT INTO enrollments VALUES (11,12,4)")
    db.execute("INSERT INTO enrollments VALUES (12,13,1)")
    db.execute("INSERT INTO enrollments VALUES (13,13,2)")
    db.execute("INSERT INTO enrollments VALUES (14,13,3)")
    db.execute("INSERT INTO enrollments VALUES (15,13,4)")

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

    db.execute("""INSERT INTO support_tickets VALUES
        (1,9,1,'Workstation not booting in ITL lab B','The workstation at row 3 seat 7 will not boot past BIOS.',
         'Open',NULL,NULL,?)""",(days_ago(5),))
    db.execute("INSERT INTO assignments VALUES (1,1,'ticket',2,NULL,?,NULL)",(days_ago(5),))
    db.execute("INSERT INTO status_changes VALUES (1,1,'ticket',NULL,'Open',9,NULL,?)",(days_ago(5),))

    db.execute("""INSERT INTO support_tickets VALUES
        (2,10,2,'Oscilloscope faulty in EE Lab','Channel 2 on oscilloscope BK-7 shows no signal.',
         'In Progress',NULL,NULL,?)""",(days_ago(10),))
    db.execute("INSERT INTO assignments VALUES (2,2,'ticket',3,5,?,NULL)",(days_ago(10),))
    db.execute("INSERT INTO status_changes VALUES (2,2,'ticket',NULL,'Open',10,NULL,?)",(days_ago(10),))
    db.execute("INSERT INTO status_changes VALUES (3,2,'ticket','Open','In Progress',5,'Investigating.',?)",(days_ago(8),))

    db.execute("""INSERT INTO support_tickets VALUES
        (3,11,3,'Cannot submit coursework on QMplus','The submission portal returns a 500 error.',
         'Resolved','Server-side upload limit increased to 50 MB.',?,?)""",(days_ago(1), days_ago(3)))
    db.execute("INSERT INTO assignments VALUES (3,3,'ticket',1,2,?,NULL)",(days_ago(4),))
    db.execute("INSERT INTO status_changes VALUES (4,3,'ticket',NULL,'Open',11,NULL,?)",(days_ago(4),))
    db.execute("INSERT INTO status_changes VALUES (5,3,'ticket','Open','Resolved',2,'Upload limit increased.',?)",(days_ago(1),))

    db.execute("""INSERT INTO support_tickets VALUES
        (4,9,1,'Cannot log in to lab machines','My QMUL credentials are rejected on every ITL machine I try.',
         'Open',NULL,NULL,?)""",(days_ago(2),))
    db.execute("INSERT INTO assignments VALUES (4,4,'ticket',2,NULL,?,NULL)",(days_ago(2),))
    db.execute("INSERT INTO status_changes VALUES (6,4,'ticket',NULL,'Open',9,NULL,?)",(days_ago(2),))

    # ── Sample EC Applications ────────────────────────────────────────────
    db.execute("""INSERT INTO ec_applications VALUES
        (1,9,1,1,'Year 2','Medical','I was hospitalised for three days prior to the submission deadline.',
         'Approved',0,'Extension of 5 days granted.',?,?)""",(days_ago(1), days_ago(12)))
    db.execute("INSERT INTO assignments VALUES (5,1,'ec',1,NULL,?,NULL)",(days_ago(12),))
    db.execute("INSERT INTO status_changes VALUES (7,1,'ec',NULL,'Submitted',9,NULL,?)",(days_ago(12),))
    db.execute("INSERT INTO status_changes VALUES (8,1,'ec','Submitted','Approved',2,'Extension granted.',?)",(days_ago(1),))

    db.execute("""INSERT INTO ec_applications VALUES
        (2,10,3,5,'Year 2','Personal','Family emergency on the day of the assessment.',
         'Under Review',0,NULL,NULL,?)""",(days_ago(6),))
    db.execute("INSERT INTO assignments VALUES (6,2,'ec',1,NULL,?,NULL)",(days_ago(6),))
    db.execute("INSERT INTO status_changes VALUES (9,2,'ec',NULL,'Submitted',10,NULL,?)",(days_ago(6),))
    db.execute("INSERT INTO status_changes VALUES (10,2,'ec','Submitted','Under Review',2,NULL,?)",(days_ago(4),))

    db.execute("""INSERT INTO ec_applications VALUES
        (3,11,1,2,'Year 3','Mental Health','Severe anxiety prevented me from completing the exam.',
         'More Evidence Needed',0,'Please upload a letter from your GP.',NULL,?)""",(days_ago(9),))
    db.execute("INSERT INTO assignments VALUES (7,3,'ec',1,NULL,?,NULL)",(days_ago(9),))
    db.execute("INSERT INTO status_changes VALUES (11,3,'ec',NULL,'Submitted',11,NULL,?)",(days_ago(9),))
    db.execute("INSERT INTO status_changes VALUES (12,3,'ec','Submitted','More Evidence Needed',2,'GP letter required.',?)",(days_ago(5),))

    # ── Comments ──────────────────────────────────────────────────────────
    db.execute(f"""INSERT INTO comments VALUES
        (1,2,'ticket',5,'I have checked the oscilloscope and ordered a replacement probe.','public','{days_ago(7)}')""")
    db.execute(f"""INSERT INTO comments VALUES
        (2,1,'ec',2,'We have received your application and will review it shortly.','public','{days_ago(11)}')""")

    db.commit()
    db.close()
    print("Database initialised successfully.")
    print()
    print("═" * 50)
    print("  TEST ACCOUNTS FOR DEMO")
    print("═" * 50)
    print()
    print("  Admin:             admin@qmul.ac.uk       / password")
    print("  SST Admin:         sst@qmul.ac.uk         / password")
    print("  Student:           student@qmul.ac.uk     / password")
    print("  Student 2:         student2@qmul.ac.uk    / password")
    print("  ITS Staff:         its@qmul.ac.uk         / password")
    print("  Lab Technician:    lab@qmul.ac.uk         / password")
    print("  Module Organiser:  organiser@qmul.ac.uk   / password")
    print()


if __name__ == '__main__':
    init_db()