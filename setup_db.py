"""
Database setup script.
Run once: python setup_db.py
Creates all tables and inserts test data for every role.
"""

import sqlite3
import os
from datetime import datetime, timedelta

DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')


def setup_database():
    """Create tables and seed data."""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # ──────────────────────────────────────
    # CREATE TABLES
    # ──────────────────────────────────────

    c.executescript('''
        DROP TABLE IF EXISTS status_changes;
        DROP TABLE IF EXISTS comments;
        DROP TABLE IF EXISTS attachments;
        DROP TABLE IF EXISTS assignments;
        DROP TABLE IF EXISTS ec_applications;
        DROP TABLE IF EXISTS support_tickets;
        DROP TABLE IF EXISTS assessments;
        DROP TABLE IF EXISTS modules;
        DROP TABLE IF EXISTS categories;
        DROP TABLE IF EXISTS teams;
        DROP TABLE IF EXISTS users;

        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'sst_admin', 'its_staff', 'lab_technician', 'module_organiser'))
        );

        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            team_type TEXT NOT NULL
        );

        CREATE TABLE categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            default_team_id INTEGER,
            FOREIGN KEY (default_team_id) REFERENCES teams(team_id)
        );

        CREATE TABLE modules (
            module_id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_code TEXT NOT NULL,
            title TEXT NOT NULL,
            organiser_id INTEGER,
            FOREIGN KEY (organiser_id) REFERENCES users(user_id)
        );

        CREATE TABLE assessments (
            assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            due_date TEXT,
            FOREIGN KEY (module_id) REFERENCES modules(module_id)
        );

        CREATE TABLE support_tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            category_id INTEGER,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'New' CHECK(status IN ('New', 'In Progress', 'Resolved', 'Closed')),
            resolution TEXT,
            resolved_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (creator_id) REFERENCES users(user_id),
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        );

        CREATE TABLE ec_applications (
            ec_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            module_id INTEGER NOT NULL,
            assessment_id INTEGER,
            year_group TEXT,
            reason TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Submitted' CHECK(status IN ('Submitted', 'Under Review', 'Approved', 'Rejected', 'More Evidence Required')),
            decision_notes TEXT,
            decision_date TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES users(user_id),
            FOREIGN KEY (module_id) REFERENCES modules(module_id),
            FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id)
        );

        CREATE TABLE assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            case_type TEXT NOT NULL CHECK(case_type IN ('ticket', 'ec')),
            team_id INTEGER NOT NULL,
            assigned_at TEXT NOT NULL,
            unassigned_at TEXT,
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        );

        CREATE TABLE comments (
            comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            case_type TEXT NOT NULL CHECK(case_type IN ('ticket', 'ec')),
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            visibility TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public', 'internal')),
            created_at TEXT NOT NULL,
            FOREIGN KEY (author_id) REFERENCES users(user_id)
        );

        CREATE TABLE attachments (
            attachment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            case_type TEXT NOT NULL CHECK(case_type IN ('ticket', 'ec')),
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        );

        CREATE TABLE status_changes (
            change_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            case_type TEXT NOT NULL CHECK(case_type IN ('ticket', 'ec')),
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by INTEGER NOT NULL,
            changed_at TEXT NOT NULL,
            FOREIGN KEY (changed_by) REFERENCES users(user_id)
        );
    ''')

    # ──────────────────────────────────────
    # SEED DATA
    # ──────────────────────────────────────

    # Users (one per role for demo)
    users = [
        ('student@qmul.ac.uk',    'password', 'Alex Johnson',     'student'),
        ('student2@qmul.ac.uk',   'password', 'Priya Patel',      'student'),
        ('sst@qmul.ac.uk',        'password', 'Sarah Williams',   'sst_admin'),
        ('its@qmul.ac.uk',        'password', 'James Chen',       'its_staff'),
        ('lab@qmul.ac.uk',        'password', 'Maria Garcia',     'lab_technician'),
        ('organiser@qmul.ac.uk',  'password', 'Dr. David Brown',  'module_organiser'),
    ]
    c.executemany('INSERT INTO users (email, password, name, role) VALUES (?, ?, ?, ?)', users)

    # Teams
    teams = [
        ('Student Support Team', 'sst'),
        ('EECS IT Services',     'its'),
        ('EE Lab Technicians',   'lab'),
    ]
    c.executemany('INSERT INTO teams (name, team_type) VALUES (?, ?)', teams)

    # Categories (with default team assignment)
    categories = [
        ('ITL Issue',           2),  # -> ITS team
        ('EE Lab Issue',        3),  # -> Lab team
        ('Submission Issue',    1),  # -> SST
        ('Access Issue',        2),  # -> ITS
        ('Service Availability', 1), # -> SST
        ('General Enquiry',     1),  # -> SST
    ]
    c.executemany('INSERT INTO categories (name, default_team_id) VALUES (?, ?)', categories)

    # Modules (organiser_id = 6 = Dr. David Brown)
    modules = [
        ('ECS506U', 'Software Engineering',                6),
        ('ECS414U', 'Operating Systems',                   6),
        ('ECS522U', 'Graphical User Interfaces',           6),
        ('ECS518U', 'Embedded Systems',                    6),
    ]
    c.executemany('INSERT INTO modules (module_code, title, organiser_id) VALUES (?, ?, ?)', modules)

    # Assessments
    assessments = [
        (1, 'Group Project',    '2026-04-15'),
        (1, 'Final Exam',       '2026-05-20'),
        (2, 'Coursework 1',     '2026-03-01'),
        (2, 'Final Exam',       '2026-05-18'),
        (3, 'Coursework 1',     '2026-03-15'),
        (4, 'Lab Report',       '2026-04-01'),
    ]
    c.executemany('INSERT INTO assessments (module_id, name, due_date) VALUES (?, ?, ?)', assessments)

    # ── Sample tickets (so the demo isn't empty) ──

    now = datetime.now()

    # Ticket 1: ITL issue (New)
    c.execute(
        'INSERT INTO support_tickets (creator_id, category_id, title, description, status, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (1, 1, 'ITL PC not turning on in Room 2.01',
         'The PC at desk 14 in ITL Room 2.01 does not power on. The monitor shows no signal and the power button light is off.',
         'New', (now - timedelta(days=2)).isoformat())
    )
    c.execute('INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
              (1, 'ticket', 2, (now - timedelta(days=2)).isoformat()))
    c.execute('INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
              'VALUES (?, ?, ?, ?, ?, ?)',
              (1, 'ticket', None, 'New', 1, (now - timedelta(days=2)).isoformat()))

    # Ticket 2: EE Lab issue (In Progress)
    c.execute(
        'INSERT INTO support_tickets (creator_id, category_id, title, description, status, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (2, 2, 'Oscilloscope not calibrating in Lab B',
         'The Tektronix oscilloscope at bench 7 in EE Lab B is displaying incorrect readings and will not auto-calibrate.',
         'In Progress', (now - timedelta(days=5)).isoformat())
    )
    c.execute('INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
              (2, 'ticket', 3, (now - timedelta(days=5)).isoformat()))
    c.execute('INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
              'VALUES (?, ?, ?, ?, ?, ?)',
              (2, 'ticket', None, 'New', 2, (now - timedelta(days=5)).isoformat()))
    c.execute('INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
              'VALUES (?, ?, ?, ?, ?, ?)',
              (2, 'ticket', 'New', 'In Progress', 5, (now - timedelta(days=3)).isoformat()))
    c.execute('INSERT INTO comments (case_id, case_type, author_id, content, visibility, created_at) '
              'VALUES (?, ?, ?, ?, ?, ?)',
              (2, 'ticket', 5, 'Investigating the issue. Will check the probe connections and run diagnostics.',
               'public', (now - timedelta(days=3)).isoformat()))

    # Ticket 3: Submission issue (Resolved)
    c.execute(
        'INSERT INTO support_tickets (creator_id, category_id, title, description, status, resolution, resolved_at, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (1, 3, 'Cannot submit coursework on QMplus',
         'When I try to upload my PDF for ECS506U coursework, QMplus shows a "file too large" error even though the file is only 2MB.',
         'Resolved', 'The upload limit was temporarily reduced during maintenance. This has been fixed.',
         (now - timedelta(days=1)).isoformat(), (now - timedelta(days=4)).isoformat())
    )
    c.execute('INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
              (3, 'ticket', 1, (now - timedelta(days=4)).isoformat()))

    # ── Sample EC applications ──

    # EC 1: Submitted (waiting for review)
    c.execute(
        'INSERT INTO ec_applications (student_id, module_id, assessment_id, year_group, reason, description, status, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (1, 1, 1, 'Year 2', 'Medical',
         'I was hospitalised for 5 days due to an emergency appendectomy and was unable to work on the group project during the final sprint.',
         'Submitted', (now - timedelta(days=1)).isoformat())
    )
    c.execute('INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
              (1, 'ec', 1, (now - timedelta(days=1)).isoformat()))
    c.execute('INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
              'VALUES (?, ?, ?, ?, ?, ?)',
              (1, 'ec', None, 'Submitted', 1, (now - timedelta(days=1)).isoformat()))

    # EC 2: Approved
    c.execute(
        'INSERT INTO ec_applications (student_id, module_id, assessment_id, year_group, reason, description, status, decision_notes, decision_date, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (2, 2, 3, 'Year 2', 'Bereavement',
         'A close family member passed away and I was unable to complete Coursework 1 by the deadline.',
         'Approved', 'Evidence verified. Extension granted until 15 March.',
         (now - timedelta(days=3)).isoformat(), (now - timedelta(days=10)).isoformat())
    )

    conn.commit()
    conn.close()
    print("Database created and seeded successfully!")
    print(f"Database file: {DATABASE}")
    print()
    print("═" * 50)
    print("  TEST ACCOUNTS FOR DEMO")
    print("═" * 50)
    print()
    print("  Student:           student@qmul.ac.uk     / password")
    print("  Student 2:         student2@qmul.ac.uk    / password")
    print("  SST Admin:         sst@qmul.ac.uk         / password")
    print("  ITS Staff:         its@qmul.ac.uk         / password")
    print("  Lab Technician:    lab@qmul.ac.uk         / password")
    print("  Module Organiser:  organiser@qmul.ac.uk   / password")
    print()


if __name__ == '__main__':
    setup_database()
