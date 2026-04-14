"""
Database initialisation script – Group 36 prototype.
Run with: python3 init_db.py
Wipes and recreates all tables with updated schema + seed data.
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
            email      TEXT UNIQUE NOT NULL,
            password   TEXT NOT NULL,
            name       TEXT NOT NULL,
            role       TEXT NOT NULL CHECK(role IN (
                'student','sst_admin','its_staff','lab_technician','module_organiser'
            )),
            year_group TEXT DEFAULT NULL
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
            year_level   INTEGER NOT NULL DEFAULT 1,
            organiser_id INTEGER,
            FOREIGN KEY (organiser_id) REFERENCES users(user_id)
        )
    """)

    # ── ENROLLMENTS ───────────────────────────────────────────────────────
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
    # Action Required replaces More Evidence Needed for clarity
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
                    'Action Required','On Hold','Withdrawn'
                )),
            is_draft       INTEGER NOT NULL DEFAULT 0,
            decision_notes TEXT,
            decision_date  TEXT,
            created_at     TEXT NOT NULL,
            FOREIGN KEY (student_id)    REFERENCES users(user_id),
            FOREIGN KEY (module_id)     REFERENCES modules(module_id),
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
            description  TEXT DEFAULT NULL,
            service_type TEXT NOT NULL DEFAULT 'digital'
                CHECK(service_type IN ('physical','digital')),
            status       TEXT NOT NULL DEFAULT 'operational'
                CHECK(status IN ('operational','degraded','outage','maintenance')),
            last_updated TEXT NOT NULL
        )
    """)

    # ══════════════════════════════════════════════════════════════════════
    # SEED DATA
    # ══════════════════════════════════════════════════════════════════════
    now = datetime.now()

    def ts(days_ago=0, hours=0):
        return (now - timedelta(days=days_ago, hours=hours)).isoformat()

    # ── Teams ─────────────────────────────────────────────────────────────
    db.execute("INSERT INTO teams VALUES (1,'Student Support Team','SST')")
    db.execute("INSERT INTO teams VALUES (2,'EECS IT Services','ITS')")
    db.execute("INSERT INTO teams VALUES (3,'EE Lab Technicians','LAB')")

    # ── Categories ────────────────────────────────────────────────────────
    # SST handles: Submission Issue, Service Availability, General Enquiry
    # ITS handles: ITL Issue, Access & Account Issue
    # LAB handles: EE Lab Issue
    db.execute("INSERT INTO categories VALUES (1,'ITL Issue',2)")
    db.execute("INSERT INTO categories VALUES (2,'EE Lab Issue',3)")
    db.execute("INSERT INTO categories VALUES (3,'Submission Issue',1)")
    db.execute("INSERT INTO categories VALUES (4,'Access & Account Issue',2)")
    db.execute("INSERT INTO categories VALUES (5,'Service Availability',1)")
    db.execute("INSERT INTO categories VALUES (6,'General Enquiry',1)")

    # ── Users (user_id, email, password, name, role, year_group) ──────────
    # SST (2 admins)
    db.execute("INSERT INTO users VALUES (1,'sst@qmul.ac.uk','password','Sarah Williams','sst_admin',NULL)")
    db.execute("INSERT INTO users VALUES (2,'sst2@qmul.ac.uk','password','Mark Thompson','sst_admin',NULL)")
    # ITS (2 staff)
    db.execute("INSERT INTO users VALUES (3,'its@qmul.ac.uk','password','James Chen','its_staff',NULL)")
    db.execute("INSERT INTO users VALUES (4,'its2@qmul.ac.uk','password','Olivia Harris','its_staff',NULL)")
    # Lab (2 technicians)
    db.execute("INSERT INTO users VALUES (5,'lab@qmul.ac.uk','password','Maria Garcia','lab_technician',NULL)")
    db.execute("INSERT INTO users VALUES (6,'lab2@qmul.ac.uk','password','Tom Wright','lab_technician',NULL)")
    # Module Organisers (2)
    db.execute("INSERT INTO users VALUES (7,'organiser@qmul.ac.uk','password','Dr. David Brown','module_organiser',NULL)")
    db.execute("INSERT INTO users VALUES (8,'organiser2@qmul.ac.uk','password','Dr. Aisha Khan','module_organiser',NULL)")
    # Students – year_group stored on the user record so EC form auto-fills it
    db.execute("INSERT INTO users VALUES (9,'year1@qmul.ac.uk','password','Emma Clarke','student','Year 1')")
    db.execute("INSERT INTO users VALUES (10,'year2@qmul.ac.uk','password','James Patel','student','Year 2')")
    db.execute("INSERT INTO users VALUES (11,'year3@qmul.ac.uk','password','Sophie Adams','student','Year 3')")
    db.execute("INSERT INTO users VALUES (12,'student@qmul.ac.uk','password','Alex Johnson','student','Year 2')")
    db.execute("INSERT INTO users VALUES (13,'student2@qmul.ac.uk','password','Priya Patel','student','Year 1')")

    # ── Modules ───────────────────────────────────────────────────────────
    # Year 1 modules (organiser: Dr. Brown)
    db.execute("INSERT INTO modules VALUES (1,'ECS101U','Introduction to Programming',1,7)")
    db.execute("INSERT INTO modules VALUES (2,'ECS102U','Mathematics for Engineers',1,7)")
    db.execute("INSERT INTO modules VALUES (3,'ECS103U','Digital Systems',1,7)")
    # Year 2 modules (organiser: Dr. Brown & Dr. Khan)
    db.execute("INSERT INTO modules VALUES (4,'ECS201U','Data Structures and Algorithms',2,7)")
    db.execute("INSERT INTO modules VALUES (5,'ECS202U','Operating Systems',2,8)")
    db.execute("INSERT INTO modules VALUES (6,'ECS203U','Software Engineering',2,8)")
    # Year 3 modules (organiser: Dr. Khan)
    db.execute("INSERT INTO modules VALUES (7,'ECS301U','Embedded Systems',3,8)")
    db.execute("INSERT INTO modules VALUES (8,'ECS302U','Networks and Distributed Systems',3,8)")
    db.execute("INSERT INTO modules VALUES (9,'ECS303U','Advanced Software Architecture',3,8)")

    # ── Enrollments ───────────────────────────────────────────────────────
    # Emma (Year 1) – all Year 1 modules
    db.execute("INSERT INTO enrollments VALUES (1,9,1)")
    db.execute("INSERT INTO enrollments VALUES (2,9,2)")
    db.execute("INSERT INTO enrollments VALUES (3,9,3)")
    # James (Year 2) – all Year 2 modules
    db.execute("INSERT INTO enrollments VALUES (4,10,4)")
    db.execute("INSERT INTO enrollments VALUES (5,10,5)")
    db.execute("INSERT INTO enrollments VALUES (6,10,6)")
    # Sophie (Year 3) – all Year 3 modules
    db.execute("INSERT INTO enrollments VALUES (7,11,7)")
    db.execute("INSERT INTO enrollments VALUES (8,11,8)")
    db.execute("INSERT INTO enrollments VALUES (9,11,9)")
    # Alex (extra) – mix of Year 2 & 3
    db.execute("INSERT INTO enrollments VALUES (10,12,5)")
    db.execute("INSERT INTO enrollments VALUES (11,12,7)")
    # Priya (extra) – mix of Year 1 & 2
    db.execute("INSERT INTO enrollments VALUES (12,13,2)")
    db.execute("INSERT INTO enrollments VALUES (13,13,4)")

    # ── Assessments ───────────────────────────────────────────────────────
    db.execute("INSERT INTO assessments VALUES (1,1,'Lab Exercise 1','2026-02-15')")
    db.execute("INSERT INTO assessments VALUES (2,1,'Coursework 1','2026-03-01')")
    db.execute("INSERT INTO assessments VALUES (3,1,'Final Exam','2026-05-10')")
    db.execute("INSERT INTO assessments VALUES (4,2,'Problem Set 1','2026-02-20')")
    db.execute("INSERT INTO assessments VALUES (5,2,'Midterm Test','2026-03-15')")
    db.execute("INSERT INTO assessments VALUES (6,3,'Lab Report','2026-03-10')")
    db.execute("INSERT INTO assessments VALUES (7,4,'Coursework 1','2026-03-05')")
    db.execute("INSERT INTO assessments VALUES (8,4,'Final Exam','2026-05-15')")
    db.execute("INSERT INTO assessments VALUES (9,5,'Coursework 1','2026-03-01')")
    db.execute("INSERT INTO assessments VALUES (10,5,'Final Exam','2026-05-18')")
    db.execute("INSERT INTO assessments VALUES (11,6,'Group Project','2026-04-15')")
    db.execute("INSERT INTO assessments VALUES (12,6,'Final Exam','2026-05-20')")
    db.execute("INSERT INTO assessments VALUES (13,7,'Lab Report','2026-04-01')")
    db.execute("INSERT INTO assessments VALUES (14,7,'Final Exam','2026-05-25')")
    db.execute("INSERT INTO assessments VALUES (15,8,'Network Design Report','2026-04-10')")
    db.execute("INSERT INTO assessments VALUES (16,8,'Final Exam','2026-05-22')")
    db.execute("INSERT INTO assessments VALUES (17,9,'Architecture Paper','2026-04-20')")
    db.execute("INSERT INTO assessments VALUES (18,9,'Final Exam','2026-05-28')")

    # ── Service Status ────────────────────────────────────────────────────
    # Physical locations
    db.execute(f"INSERT INTO service_status VALUES (1,'Engineering Lab','Electronics and computing lab for ECS students — hardware, benches and specialist equipment','physical','operational','{ts()}')")
    db.execute(f"INSERT INTO service_status VALUES (2,'ITL (IT Learning Suite)','Managed computer labs with discipline-specific software and printing facilities','physical','operational','{ts()}')")
    db.execute(f"INSERT INTO service_status VALUES (3,'Temporary Building','Additional teaching and lab space — check room bookings before travelling','physical','operational','{ts()}')")
    db.execute(f"INSERT INTO service_status VALUES (4,'Library','Main library — books, study booths, silent zones and 24-hour access during term','physical','operational','{ts()}')")
    db.execute(f"INSERT INTO service_status VALUES (5,'The Nest','Student hub with food, social spaces and quiet study areas','physical','operational','{ts()}')")
    db.execute(f"INSERT INTO service_status VALUES (6,'The Hive','Student services and collaborative study hub — drop-ins and support services','physical','operational','{ts()}')")
    # Digital platforms
    db.execute(f"INSERT INTO service_status VALUES (7,'MySIS','Student information system — module registration, grades, timetable and official records','digital','operational','{ts()}')")
    db.execute(f"INSERT INTO service_status VALUES (8,'QMplus','Learning platform — module content, readings, assignment submission and announcements','digital','operational','{ts()}')")

    # ══════════════════════════════════════════════════════════════════════
    # TICKETS  (ITS tickets handled by ITS, Lab by Lab, SST by SST)
    # ══════════════════════════════════════════════════════════════════════

    # --- ITS Ticket 1: Open, assigned to James Chen (user 3) ---------------
    db.execute(f"INSERT INTO support_tickets VALUES (1,9,1,'Workstation not booting in ITL Lab B','Row 3, seat 7 will not boot past BIOS screen.','Open',NULL,NULL,'{ts(5)}')")
    db.execute(f"INSERT INTO assignments VALUES (1,1,'ticket',2,3,'{ts(5)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (1,1,'ticket',NULL,'Open',9,NULL,'{ts(5)}')")

    # --- ITS Ticket 2: In Progress, assigned to Olivia Harris (user 4) ----
    db.execute(f"INSERT INTO support_tickets VALUES (2,10,4,'Cannot log into QMUL account','My credentials stopped working across all QMUL systems.','In Progress',NULL,NULL,'{ts(8)}')")
    db.execute(f"INSERT INTO assignments VALUES (2,2,'ticket',2,4,'{ts(8)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (2,2,'ticket',NULL,'Open',10,NULL,'{ts(8)}')")
    db.execute(f"INSERT INTO status_changes VALUES (3,2,'ticket','Open','In Progress',4,'Investigating with IT identity team.','{ts(6)}')")
    db.execute(f"INSERT INTO comments VALUES (1,2,'ticket',4,'I have contacted the identity management team. Your account should be restored within 24 hours.','public','{ts(6)}')")

    # --- ITS Ticket 3: Resolved, assigned to James Chen -------------------
    db.execute(f"INSERT INTO support_tickets VALUES (3,11,1,'Software not installed on ITL machines','MATLAB R2024 is missing from all ITL workstations.','Resolved','MATLAB has been deployed to all ITL workstations via SCCM.','{ts(1)}','{ts(10)}')")
    db.execute(f"INSERT INTO assignments VALUES (3,3,'ticket',2,3,'{ts(10)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (4,3,'ticket',NULL,'Open',11,NULL,'{ts(10)}')")
    db.execute(f"INSERT INTO status_changes VALUES (5,3,'ticket','Open','In Progress',3,'Rolling out MATLAB via software centre.','{ts(7)}')")
    db.execute(f"INSERT INTO status_changes VALUES (6,3,'ticket','In Progress','Resolved',3,'MATLAB deployed successfully.','{ts(1)}')")

    # --- Lab Ticket 1: Open, assigned to Maria Garcia (user 5) ------------
    db.execute(f"INSERT INTO support_tickets VALUES (4,9,2,'Oscilloscope faulty in EE Lab A','Channel 2 on oscilloscope unit BK-7 shows no signal output.','Open',NULL,NULL,'{ts(3)}')")
    db.execute(f"INSERT INTO assignments VALUES (4,4,'ticket',3,5,'{ts(3)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (7,4,'ticket',NULL,'Open',9,NULL,'{ts(3)}')")

    # --- Lab Ticket 2: In Progress, assigned to Tom Wright (user 6) -------
    db.execute(f"INSERT INTO support_tickets VALUES (5,10,2,'Soldering station broken','Station 4 in EE Lab B will not heat up.','In Progress',NULL,NULL,'{ts(6)}')")
    db.execute(f"INSERT INTO assignments VALUES (5,5,'ticket',3,6,'{ts(6)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (8,5,'ticket',NULL,'Open',10,NULL,'{ts(6)}')")
    db.execute(f"INSERT INTO status_changes VALUES (9,5,'ticket','Open','In Progress',6,'Replacement heating element ordered.','{ts(4)}')")
    db.execute(f"INSERT INTO comments VALUES (2,5,'ticket',6,'Replacement part expected by Friday. Will update once fitted.','public','{ts(4)}')")

    # --- Lab Ticket 3: Resolved, assigned to Maria Garcia ----------------
    db.execute(f"INSERT INTO support_tickets VALUES (6,11,2,'PCB drill press misaligned','The drill press in EE Lab B is misaligned by approx 2mm.','Resolved','Drill press recalibrated and test cuts verified accurate.','{ts(1)}','{ts(9)}')")
    db.execute(f"INSERT INTO assignments VALUES (6,6,'ticket',3,5,'{ts(9)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (10,6,'ticket',NULL,'Open',11,NULL,'{ts(9)}')")
    db.execute(f"INSERT INTO status_changes VALUES (11,6,'ticket','Open','In Progress',5,'Checking calibration.','{ts(5)}')")
    db.execute(f"INSERT INTO status_changes VALUES (12,6,'ticket','In Progress','Resolved',5,'Recalibrated successfully.','{ts(1)}')")

    # --- SST Ticket 1: Open, assigned to Sarah Williams (user 1) ----------
    db.execute(f"INSERT INTO support_tickets VALUES (7,9,3,'Cannot submit coursework on QMplus','The submission portal returns a 500 error when I upload my PDF.','Open',NULL,NULL,'{ts(2)}')")
    db.execute(f"INSERT INTO assignments VALUES (7,7,'ticket',1,1,'{ts(2)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (13,7,'ticket',NULL,'Open',9,NULL,'{ts(2)}')")

    # --- SST Ticket 2: In Progress, assigned to Mark Thompson (user 2) ----
    db.execute(f"INSERT INTO support_tickets VALUES (8,10,6,'Query about deadline extension policy','I want to understand the formal process for requesting a deadline extension.','In Progress',NULL,NULL,'{ts(7)}')")
    db.execute(f"INSERT INTO assignments VALUES (8,8,'ticket',1,2,'{ts(7)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (14,8,'ticket',NULL,'Open',10,NULL,'{ts(7)}')")
    db.execute(f"INSERT INTO status_changes VALUES (15,8,'ticket','Open','In Progress',2,'Reviewing university policy documents.','{ts(5)}')")
    db.execute(f"INSERT INTO comments VALUES (3,8,'ticket',2,'The formal extension request process is outlined in the Student Handbook section 4.3. I will email you a direct link.','public','{ts(5)}')")

    # --- SST Ticket 3: Resolved (Sarah Williams) --------------------------
    db.execute(f"INSERT INTO support_tickets VALUES (9,11,5,'QMplus was down for 2 hours','Could not access any materials or submit work between 10am-12pm.','Resolved','Confirmed outage acknowledged. Submission deadline extended by 24h for affected students.','{ts(1)}','{ts(11)}')")
    db.execute(f"INSERT INTO assignments VALUES (9,9,'ticket',1,1,'{ts(11)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (16,9,'ticket',NULL,'Open',11,NULL,'{ts(11)}')")
    db.execute(f"INSERT INTO status_changes VALUES (17,9,'ticket','Open','Resolved',1,'Deadline extended for affected students.','{ts(1)}')")

    # --- Withdrawn ticket (student withdrew) --------------------------------
    db.execute(f"INSERT INTO support_tickets VALUES (10,12,6,'Wrong module listed on transcript','My transcript shows wrong module code for ECS202U.','Withdrawn',NULL,NULL,'{ts(14)}')")
    db.execute(f"INSERT INTO assignments VALUES (10,10,'ticket',1,NULL,'{ts(14)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (18,10,'ticket',NULL,'Open',12,NULL,'{ts(14)}')")
    db.execute(f"INSERT INTO status_changes VALUES (19,10,'ticket','Open','Withdrawn',12,'Student withdrew the request.','{ts(12)}')")

    # ══════════════════════════════════════════════════════════════════════
    # EC APPLICATIONS
    # ══════════════════════════════════════════════════════════════════════

    # EC 1 – Approved (Emma, Year 1, module 1)
    db.execute(f"INSERT INTO ec_applications VALUES (1,9,1,2,'Year 1','Medical','I was hospitalised for three days prior to the submission deadline due to appendicitis.','Approved',0,'5-day extension granted. Please resubmit by the extended deadline.','{ts(1)}','{ts(12)}')")
    db.execute(f"INSERT INTO assignments VALUES (11,1,'ec',1,1,'{ts(12)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (20,1,'ec',NULL,'Submitted',9,NULL,'{ts(12)}')")
    db.execute(f"INSERT INTO status_changes VALUES (21,1,'ec','Submitted','Under Review',1,NULL,'{ts(10)}')")
    db.execute(f"INSERT INTO status_changes VALUES (22,1,'ec','Under Review','Approved',1,'5-day extension granted.','{ts(1)}')")
    db.execute(f"INSERT INTO comments VALUES (4,1,'ec',1,'We have reviewed your medical documentation. Extension approved.','public','{ts(1)}')")

    # EC 2 – Under Review (James, Year 2, module 5)
    db.execute(f"INSERT INTO ec_applications VALUES (2,10,5,9,'Year 2','Personal','Family emergency on the day of the coursework deadline required me to travel home.','Under Review',0,NULL,NULL,'{ts(6)}')")
    db.execute(f"INSERT INTO assignments VALUES (12,2,'ec',1,2,'{ts(6)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (23,2,'ec',NULL,'Submitted',10,NULL,'{ts(6)}')")
    db.execute(f"INSERT INTO status_changes VALUES (24,2,'ec','Submitted','Under Review',2,'Reviewing supporting documents.','{ts(4)}')")

    # EC 3 – Action Required (Sophie, Year 3, module 7)
    db.execute(f"INSERT INTO ec_applications VALUES (3,11,7,13,'Year 3','Mental Health','Severe anxiety and panic attacks prevented me from attending the lab session.','Action Required',0,'Please upload a letter from your GP, counsellor, or QMUL Student Wellbeing.',NULL,'{ts(9)}')")
    db.execute(f"INSERT INTO assignments VALUES (13,3,'ec',1,1,'{ts(9)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (25,3,'ec',NULL,'Submitted',11,NULL,'{ts(9)}')")
    db.execute(f"INSERT INTO status_changes VALUES (26,3,'ec','Submitted','Action Required',1,'GP or wellbeing letter required.','{ts(5)}')")
    db.execute(f"INSERT INTO comments VALUES (5,3,'ec',1,'Please upload supporting documentation from a GP or QMUL Wellbeing service to proceed.','public','{ts(5)}')")

    # EC 4 – On Hold (Emma, Year 1, module 2)
    db.execute(f"INSERT INTO ec_applications VALUES (4,9,2,4,'Year 1','Bereavement','My grandmother passed away the week of the problem set deadline.','On Hold',0,'Awaiting confirmation of relationship from the university registry.',NULL,'{ts(14)}')")
    db.execute(f"INSERT INTO assignments VALUES (14,4,'ec',1,NULL,'{ts(14)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (27,4,'ec',NULL,'Submitted',9,NULL,'{ts(14)}')")
    db.execute(f"INSERT INTO status_changes VALUES (28,4,'ec','Submitted','On Hold',1,'Registry confirmation pending.','{ts(8)}')")

    # EC 5 – Draft (James, Year 2, module 4)
    db.execute(f"INSERT INTO ec_applications VALUES (5,10,4,7,'Year 2','Medical','I had a severe migraine during the coursework submission period.','Submitted',1,NULL,NULL,'{ts(1)}')")

    # EC 6 – Rejected (Sophie, Year 3, module 8)
    db.execute(f"INSERT INTO ec_applications VALUES (6,11,8,15,'Year 3','Other','I forgot to prepare in time for the deadline.','Rejected',0,'Insufficient grounds for EC under university policy. Forgetfulness is not an extenuating circumstance.','{ts(3)}','{ts(20)}')")
    db.execute(f"INSERT INTO assignments VALUES (15,6,'ec',1,2,'{ts(20)}',NULL)")
    db.execute(f"INSERT INTO status_changes VALUES (29,6,'ec',NULL,'Submitted',11,NULL,'{ts(20)}')")
    db.execute(f"INSERT INTO status_changes VALUES (30,6,'ec','Submitted','Rejected',2,'Insufficient grounds.','{ts(3)}')")

    # EC 7 – Withdrawn (Alex, module 5)
    db.execute(f"INSERT INTO ec_applications VALUES (7,12,5,10,'Year 2','Personal','Situation resolved itself before review.','Withdrawn',0,NULL,NULL,'{ts(15)}')")
    db.execute(f"INSERT INTO status_changes VALUES (31,7,'ec',NULL,'Submitted',12,NULL,'{ts(15)}')")
    db.execute(f"INSERT INTO status_changes VALUES (32,7,'ec','Submitted','Withdrawn',12,'Student withdrew the application.','{ts(13)}')")

    db.commit()
    db.close()
    print("Database initialised successfully.")
    print()
    print("=== LOGIN ACCOUNTS ===")
    print("STUDENTS")
    print("  year1@qmul.ac.uk   / password  – Emma Clarke  (Year 1: ECS101U, ECS102U, ECS103U)")
    print("  year2@qmul.ac.uk   / password  – James Patel  (Year 2: ECS201U, ECS202U, ECS203U)")
    print("  year3@qmul.ac.uk   / password  – Sophie Adams (Year 3: ECS301U, ECS302U, ECS303U)")
    print("SST ADMIN")
    print("  sst@qmul.ac.uk     / password  – Sarah Williams")
    print("  sst2@qmul.ac.uk    / password  – Mark Thompson")
    print("ITS STAFF")
    print("  its@qmul.ac.uk     / password  – James Chen   (handles ITS tickets)")
    print("  its2@qmul.ac.uk    / password  – Olivia Harris (handles ITS tickets)")
    print("LAB TECHNICIAN")
    print("  lab@qmul.ac.uk     / password  – Maria Garcia  (handles Lab tickets)")
    print("  lab2@qmul.ac.uk    / password  – Tom Wright    (handles Lab tickets)")
    print("MODULE ORGANISER")
    print("  organiser@qmul.ac.uk  / password  – Dr. David Brown (Year 1 & 2)")
    print("  organiser2@qmul.ac.uk / password  – Dr. Aisha Khan  (Year 2 & 3)")


if __name__ == '__main__':
    init_db()
