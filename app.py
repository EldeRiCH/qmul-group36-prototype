"""
QMUL Issues and Feedback System - Prototype
Group 36 | ECS506U Software Engineering

Flask app with server-rendered Jinja2 templates + Bootstrap 5 + SQLite.
Run with: python app.py
"""

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, send_from_directory
)
from functools import wraps
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'qmul-group36-prototype-key'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}

DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')

# Which services each team type can suggest changes for (by service_id)
SERVICE_TEAM_OWNERSHIP = {
    'SST': [4, 5, 6, 7, 8],   # Library, The Nest, The Hive, MySIS, QMplus
    'ITS': [2, 3],             # ITL, Temporary Building
    'LAB': [1],                # Engineering Lab
}
# Reverse: service_id → team_type
SERVICE_OWNER = {sid: team for team, sids in SERVICE_TEAM_OWNERSHIP.items() for sid in sids}

ROLE_TEAM_TYPE = {
    'sst_admin':      'SST',
    'its_staff':      'ITS',
    'lab_technician': 'LAB',
}


# ──────────────────────────────────────────────
# DATABASE HELPERS
# ──────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def migrate_db():
    """Apply additive migrations to an existing database (safe to run repeatedly)."""
    db = sqlite3.connect(DATABASE)
    # Add service_suggestions table if missing
    db.execute("""
        CREATE TABLE IF NOT EXISTS service_suggestions (
            suggestion_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id       INTEGER NOT NULL,
            suggested_status TEXT NOT NULL,
            suggested_by     INTEGER NOT NULL,
            notes            TEXT,
            status           TEXT NOT NULL DEFAULT 'pending',
            created_at       TEXT NOT NULL,
            reviewed_by      INTEGER,
            reviewed_at      TEXT,
            review_notes     TEXT
        )
    """)
    # Add admin user if not present (INSERT OR IGNORE works because email is UNIQUE)
    db.execute(
        "INSERT OR IGNORE INTO users (email, password, name, role) VALUES (?,?,?,?)",
        ('admin@qmul.ac.uk', 'password', 'System Admin', 'admin')
    )
    db.commit()
    db.close()


# Run migrations once on startup
with app.app_context():
    if os.path.exists(DATABASE):
        migrate_db()


# ── Reference number formatters ──────────────────────────────────────────────
@app.template_filter('ticket_ref')
def ticket_ref(ticket_id):
    return f'TKT-2025-{int(ticket_id):04d}'

@app.template_filter('ec_ref')
def ec_ref(ec_id):
    return f'EC-2025-{int(ec_id):04d}'


@app.template_filter('timeago')
def timeago_filter(dt_str):
    """Convert ISO datetime string to a human-friendly 'X ago' string."""
    if not dt_str:
        return '—'
    try:
        dt = datetime.fromisoformat(str(dt_str)[:19])
        diff = datetime.now() - dt
        s = int(diff.total_seconds())
        if s < 60:
            return 'just now'
        elif s < 3600:
            m = s // 60
            return f'{m}m ago'
        elif s < 86400:
            h = s // 3600
            return f'{h}h ago'
        elif s < 7 * 86400:
            d = s // 86400
            return f'{d} day{"s" if d != 1 else ""} ago'
        else:
            return dt.strftime('%d %b %Y')
    except Exception:
        return str(dt_str)[:10]


# ──────────────────────────────────────────────
# AUTH DECORATORS
# ──────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session or session['role'] not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ──────────────────────────────────────────────
# CONTEXT PROCESSOR
# ──────────────────────────────────────────────

@app.context_processor
def inject_user():
    ctx = {}
    if 'user_id' in session:
        ctx.update({
            'current_user_id':    session['user_id'],
            'current_user_name':  session.get('name', ''),
            'current_user_role':  session.get('role', ''),
            'current_user_email': session.get('email', ''),
        })
        # Service status for navbar indicator
        services = query_db('SELECT * FROM service_status')
        any_issue = any(s['status'] != 'operational' for s in services)
        ctx['service_status_ok'] = not any_issue
        ctx['services'] = services
        # Pending suggestions count for admin navbar badge
        if session.get('role') == 'admin':
            row = query_db(
                "SELECT COUNT(*) as cnt FROM service_suggestions WHERE status = 'pending'",
                one=True
            )
            ctx['pending_suggestions_count'] = row['cnt'] if row else 0
    return ctx


# ──────────────────────────────────────────────
# AUTH ROUTES
# ──────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('login.html')

        user = query_db(
            'SELECT * FROM users WHERE email = ? AND password = ?',
            (email, password), one=True
        )
        if user:
            session['user_id']    = user['user_id']
            session['name']       = user['name']
            session['email']      = user['email']
            session['role']       = user['role']
            session['year_group'] = user['year_group']   # None for non-students
            flash(f'Welcome, {user["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'student':
        return redirect(url_for('student_dashboard'))
    elif role == 'sst_admin':
        return redirect(url_for('sst_dashboard'))
    elif role == 'its_staff':
        return redirect(url_for('its_dashboard'))
    elif role == 'lab_technician':
        return redirect(url_for('lab_dashboard'))
    elif role == 'module_organiser':
        return redirect(url_for('organiser_dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Your role is not recognised.', 'danger')
        return redirect(url_for('logout'))


# ──────────────────────────────────────────────
# FILE DOWNLOAD ROUTE (staff + student owner)
# ──────────────────────────────────────────────

@app.route('/preview/<int:attachment_id>')
@login_required
def preview_file(attachment_id):
    """Serve a file inline so the browser can display it (PDF/images)."""
    att = query_db('SELECT * FROM attachments WHERE attachment_id = ?', (attachment_id,), one=True)
    if not att:
        flash('File not found.', 'danger')
        return redirect(url_for('dashboard'))

    role = session.get('role')
    uid  = session['user_id']
    if role == 'student':
        if att['case_type'] == 'ticket':
            ticket = query_db('SELECT creator_id FROM support_tickets WHERE ticket_id = ?', (att['case_id'],), one=True)
            if not ticket or ticket['creator_id'] != uid:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard'))
        elif att['case_type'] == 'ec':
            ec = query_db('SELECT student_id FROM ec_applications WHERE ec_id = ?', (att['case_id'],), one=True)
            if not ec or ec['student_id'] != uid:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard'))

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        att['file_path'],
        as_attachment=False,          # inline – browser renders PDF/images
        download_name=att['file_name']
    )


@app.route('/download/<int:attachment_id>')
@login_required
def download_file(attachment_id):
    att = query_db('SELECT * FROM attachments WHERE attachment_id = ?', (attachment_id,), one=True)
    if not att:
        flash('File not found.', 'danger')
        return redirect(url_for('dashboard'))

    role = session.get('role')
    uid  = session['user_id']

    # Students may only download attachments on their own cases
    if role == 'student':
        if att['case_type'] == 'ticket':
            ticket = query_db('SELECT creator_id FROM support_tickets WHERE ticket_id = ?', (att['case_id'],), one=True)
            if not ticket or ticket['creator_id'] != uid:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard'))
        elif att['case_type'] == 'ec':
            ec = query_db('SELECT student_id FROM ec_applications WHERE ec_id = ?', (att['case_id'],), one=True)
            if not ec or ec['student_id'] != uid:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard'))

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        att['file_path'],
        as_attachment=True,
        download_name=att['file_name']
    )


# ──────────────────────────────────────────────
# STUDENT ROUTES
# ──────────────────────────────────────────────

@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    uid = session['user_id']
    tickets = query_db(
        'SELECT t.*, c.name as category_name FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'WHERE t.creator_id = ? ORDER BY t.created_at DESC',
        (uid,)
    )
    ecs = query_db(
        'SELECT ec.*, m.title as module_title, m.module_code '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'WHERE ec.student_id = ? ORDER BY ec.created_at DESC',
        (uid,)
    )
    # Activity feed: recent status changes on the student's cases
    activity = query_db(
        'SELECT sc.case_type, sc.case_id, sc.new_status, sc.changed_at, '
        '  COALESCE(t.title, m.module_code) as case_title '
        'FROM status_changes sc '
        'LEFT JOIN support_tickets t ON sc.case_id = t.ticket_id AND sc.case_type = "ticket" '
        'LEFT JOIN ec_applications ec ON sc.case_id = ec.ec_id AND sc.case_type = "ec" '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'WHERE (sc.case_type = "ticket" AND t.creator_id = ?) '
        '   OR (sc.case_type = "ec" AND ec.student_id = ?) '
        'ORDER BY sc.changed_at DESC LIMIT 8',
        (uid, uid)
    )
    return render_template('student/dashboard.html', tickets=tickets, ecs=ecs, activity=activity)


@app.route('/student/submit-ticket', methods=['GET', 'POST'])
@login_required
@role_required('student')
def submit_ticket():
    categories = query_db(
        'SELECT c.*, t.name as team_name, t.team_type '
        'FROM categories c LEFT JOIN teams t ON c.default_team_id = t.team_id'
    )

    if request.method == 'POST':
        category_id = request.form.get('category_id')
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()

        if not category_id or not title or not description:
            flash('Please fill in all required fields.', 'danger')
            return render_template('student/submit_ticket.html', categories=categories)

        ticket_id = execute_db(
            'INSERT INTO support_tickets (creator_id, category_id, title, description, status, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (session['user_id'], category_id, title, description, 'Open', datetime.now().isoformat())
        )

        category = query_db('SELECT * FROM categories WHERE category_id = ?', (category_id,), one=True)
        if category:
            execute_db(
                'INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
                (ticket_id, 'ticket', category['default_team_id'], datetime.now().isoformat())
            )

        # Multiple file uploads
        files = request.files.getlist('evidence')
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"ticket_{ticket_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                execute_db(
                    'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', file.filename, filename, datetime.now().isoformat())
                )

        execute_db(
            'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (ticket_id, 'ticket', None, 'Open', session['user_id'], datetime.now().isoformat())
        )

        flash(f'Ticket #{ticket_id} submitted successfully!', 'success')
        return redirect(url_for('student_dashboard'))

    return render_template('student/submit_ticket.html', categories=categories)


@app.route('/student/ticket/<int:ticket_id>/withdraw', methods=['POST'])
@login_required
@role_required('student')
def student_withdraw_ticket(ticket_id):
    ticket = query_db(
        'SELECT * FROM support_tickets WHERE ticket_id = ? AND creator_id = ?',
        (ticket_id, session['user_id']), one=True
    )
    if not ticket:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('student_dashboard'))
    if ticket['status'] in ('Resolved', 'Closed', 'Withdrawn'):
        flash('This ticket cannot be withdrawn.', 'warning')
        return redirect(url_for('student_view_ticket', ticket_id=ticket_id))

    old_status = ticket['status']
    execute_db('UPDATE support_tickets SET status = ? WHERE ticket_id = ?', ('Withdrawn', ticket_id))
    execute_db(
        'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, notes, changed_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (ticket_id, 'ticket', old_status, 'Withdrawn', session['user_id'],
         'Withdrawn by student.', datetime.now().isoformat())
    )
    flash('Ticket withdrawn.', 'info')
    return redirect(url_for('student_dashboard'))


@app.route('/student/submit-ec', methods=['GET', 'POST'])
@login_required
@role_required('student')
def submit_ec():
    uid = session['user_id']
    # Only show modules the student is enrolled in
    modules = query_db(
        'SELECT m.* FROM modules m '
        'JOIN enrollments e ON m.module_id = e.module_id '
        'WHERE e.student_id = ? ORDER BY m.module_code',
        (uid,)
    )

    if request.method == 'POST':
        module_id     = request.form.get('module_id')
        assessment_id = request.form.get('assessment_id')
        year_group    = session.get('year_group', '')
        reason        = request.form.get('reason', '').strip()
        description   = request.form.get('description', '').strip()
        is_draft      = 1 if request.form.get('save_draft') else 0
        status        = 'Submitted' if not is_draft else 'Submitted'  # drafts still use Submitted but is_draft=1

        if not module_id or not assessment_id or not reason or not description:
            flash('Please fill in all required fields.', 'danger')
            assessments = query_db('SELECT * FROM assessments WHERE module_id = ?', (module_id,)) if module_id else []
            return render_template('student/submit_ec.html', modules=modules, assessments=assessments)

        ec_id = execute_db(
            'INSERT INTO ec_applications '
            '(student_id, module_id, assessment_id, year_group, reason, description, status, is_draft, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (uid, module_id, assessment_id, year_group, reason, description,
             status, is_draft, datetime.now().isoformat())
        )

        if not is_draft:
            sst_team = query_db("SELECT team_id FROM teams WHERE team_type = 'SST'", one=True)
            if sst_team:
                execute_db(
                    'INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
                    (ec_id, 'ec', sst_team['team_id'], datetime.now().isoformat())
                )
            execute_db(
                'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (ec_id, 'ec', None, 'Submitted', uid, datetime.now().isoformat())
            )

        # Multiple file uploads
        files = request.files.getlist('evidence')
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"ec_{ec_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                execute_db(
                    'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (ec_id, 'ec', file.filename, filename, datetime.now().isoformat())
                )

        msg = f'EC Application #{ec_id} saved as draft.' if is_draft else f'EC Application #{ec_id} submitted successfully!'
        flash(msg, 'success' if not is_draft else 'info')
        return redirect(url_for('student_dashboard'))

    return render_template('student/submit_ec.html', modules=modules, assessments=[])


@app.route('/student/ec/<int:ec_id>/submit-draft', methods=['POST'])
@login_required
@role_required('student')
def student_submit_draft(ec_id):
    ec = query_db(
        'SELECT * FROM ec_applications WHERE ec_id = ? AND student_id = ?',
        (ec_id, session['user_id']), one=True
    )
    if not ec or not ec['is_draft']:
        flash('Draft not found.', 'danger')
        return redirect(url_for('student_dashboard'))

    execute_db('UPDATE ec_applications SET is_draft = 0 WHERE ec_id = ?', (ec_id,))
    sst_team = query_db("SELECT team_id FROM teams WHERE team_type = 'SST'", one=True)
    if sst_team:
        existing = query_db("SELECT * FROM assignments WHERE case_id = ? AND case_type = 'ec'", (ec_id,), one=True)
        if not existing:
            execute_db(
                'INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
                (ec_id, 'ec', sst_team['team_id'], datetime.now().isoformat())
            )
    execute_db(
        'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (ec_id, 'ec', None, 'Submitted', session['user_id'], datetime.now().isoformat())
    )
    flash(f'EC Application #{ec_id} submitted.', 'success')
    return redirect(url_for('student_dashboard'))


@app.route('/student/ec/<int:ec_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_edit_draft(ec_id):
    """Edit a saved EC draft before submitting."""
    uid = session['user_id']
    ec = query_db(
        'SELECT ec.*, m.module_code FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'WHERE ec.ec_id = ? AND ec.student_id = ? AND ec.is_draft = 1',
        (ec_id, uid), one=True
    )
    if not ec:
        flash('Draft not found or already submitted.', 'danger')
        return redirect(url_for('student_dashboard'))

    modules = query_db(
        'SELECT m.* FROM modules m '
        'JOIN enrollments e ON m.module_id = e.module_id '
        'WHERE e.student_id = ? ORDER BY m.module_code',
        (uid,)
    )
    assessments = query_db('SELECT * FROM assessments WHERE module_id = ?', (ec['module_id'],))

    if request.method == 'POST':
        module_id     = request.form.get('module_id')
        assessment_id = request.form.get('assessment_id')
        reason        = request.form.get('reason', '').strip()
        description   = request.form.get('description', '').strip()
        is_draft      = 1 if request.form.get('save_draft') else 0

        if not module_id or not assessment_id or not reason or not description:
            flash('Please fill in all required fields.', 'danger')
            return render_template('student/edit_ec.html', ec=ec, modules=modules, assessments=assessments)

        execute_db(
            'UPDATE ec_applications SET module_id = ?, assessment_id = ?, reason = ?, description = ?, is_draft = ? '
            'WHERE ec_id = ?',
            (module_id, assessment_id, reason, description, is_draft, ec_id)
        )

        # Handle additional file uploads
        files = request.files.getlist('evidence')
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"ec_{ec_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                execute_db(
                    'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (ec_id, 'ec', file.filename, filename, datetime.now().isoformat())
                )

        if not is_draft:
            sst_team = query_db("SELECT team_id FROM teams WHERE team_type = 'SST'", one=True)
            if sst_team:
                existing = query_db("SELECT * FROM assignments WHERE case_id = ? AND case_type = 'ec'", (ec_id,), one=True)
                if not existing:
                    execute_db(
                        'INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
                        (ec_id, 'ec', sst_team['team_id'], datetime.now().isoformat())
                    )
            execute_db(
                'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (ec_id, 'ec', None, 'Submitted', uid, datetime.now().isoformat())
            )
            flash('EC Application submitted successfully!', 'success')
        else:
            flash('Draft saved.', 'success')

        return redirect(url_for('student_dashboard'))

    return render_template('student/edit_ec.html', ec=ec, modules=modules, assessments=assessments)


@app.route('/student/ec/<int:ec_id>/withdraw', methods=['POST'])
@login_required
@role_required('student')
def student_withdraw_ec(ec_id):
    ec = query_db(
        'SELECT * FROM ec_applications WHERE ec_id = ? AND student_id = ?',
        (ec_id, session['user_id']), one=True
    )
    if not ec:
        flash('EC application not found.', 'danger')
        return redirect(url_for('student_dashboard'))
    if ec['status'] in ('Approved', 'Rejected', 'Withdrawn'):
        flash('This EC application cannot be withdrawn.', 'warning')
        return redirect(url_for('student_view_ec', ec_id=ec_id))

    old_status = ec['status']
    execute_db('UPDATE ec_applications SET status = ? WHERE ec_id = ?', ('Withdrawn', ec_id))
    execute_db(
        'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, notes, changed_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (ec_id, 'ec', old_status, 'Withdrawn', session['user_id'],
         'Withdrawn by student.', datetime.now().isoformat())
    )
    flash('EC application withdrawn.', 'info')
    return redirect(url_for('student_dashboard'))


@app.route('/student/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_view_ticket(ticket_id):
    ticket = query_db(
        'SELECT t.*, c.name as category_name FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'WHERE t.ticket_id = ? AND t.creator_id = ?',
        (ticket_id, session['user_id']), one=True
    )
    if not ticket:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_file' and ticket['status'] not in ('Resolved', 'Closed', 'Withdrawn'):
            files = request.files.getlist('files')
            saved = 0
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"ticket_{ticket_id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    execute_db(
                        'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (ticket_id, 'ticket', file.filename, filename, datetime.now().isoformat())
                    )
                    saved += 1
            if saved:
                flash(f'{saved} file(s) uploaded successfully.', 'success')
            else:
                flash('No valid files were uploaded.', 'warning')
        return redirect(url_for('student_view_ticket', ticket_id=ticket_id))

    comments = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? AND cm.visibility = ? ORDER BY cm.created_at ASC',
        (ticket_id, 'ticket', 'public')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ticket_id, 'ticket'))
    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ticket_id, 'ticket')
    )
    return render_template('student/view_ticket.html',
                           ticket=ticket, comments=comments,
                           attachments=attachments, history=history)


@app.route('/student/ec/<int:ec_id>', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_view_ec(ec_id):
    ec = query_db(
        'SELECT ec.*, m.title as module_title, m.module_code, '
        'a.name as assessment_name, a.due_date as assessment_due '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'LEFT JOIN assessments a ON ec.assessment_id = a.assessment_id '
        'WHERE ec.ec_id = ? AND ec.student_id = ?',
        (ec_id, session['user_id']), one=True
    )
    if not ec:
        flash('EC application not found.', 'danger')
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_file' and ec['status'] == 'Action Required':
            files = request.files.getlist('files')
            saved = 0
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"ec_{ec_id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    execute_db(
                        'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (ec_id, 'ec', file.filename, filename, datetime.now().isoformat())
                    )
                    saved += 1
            if saved:
                flash(f'{saved} file(s) uploaded successfully.', 'success')
            else:
                flash('No valid files were uploaded.', 'warning')
        return redirect(url_for('student_view_ec', ec_id=ec_id))

    comments = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? AND cm.visibility = ? ORDER BY cm.created_at ASC',
        (ec_id, 'ec', 'public')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ec_id, 'ec'))
    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ec_id, 'ec')
    )
    return render_template('student/view_ec.html',
                           ec=ec, comments=comments,
                           attachments=attachments, history=history)


# EC assessment list (AJAX helper – returns assessments for a module)
@app.route('/api/module/<int:module_id>/assessments')
@login_required
def api_module_assessments(module_id):
    from flask import jsonify
    assessments = query_db(
        'SELECT assessment_id, name, due_date FROM assessments WHERE module_id = ?', (module_id,)
    )
    return jsonify([dict(a) for a in assessments])


# ──────────────────────────────────────────────
# SST ADMIN ROUTES
# ──────────────────────────────────────────────

@app.route('/sst/dashboard')
@login_required
@role_required('sst_admin')
def sst_dashboard():
    status_filter    = request.args.get('status', '')
    category_filter  = request.args.get('category', '')
    search_query     = request.args.get('search', '').strip()
    ec_status_filter = request.args.get('ec_status', '')
    ec_search_query  = request.args.get('ec_search', '').strip()

    # SST only sees tickets assigned to the SST team (ITS and Lab handle their own)
    ticket_query = (
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'JOIN assignments a ON a.case_id = t.ticket_id AND a.case_type = ? '
        'JOIN teams tm ON a.team_id = tm.team_id '
        "WHERE tm.team_type = 'SST'"
    )
    args = ['ticket']
    if status_filter:
        ticket_query += ' AND t.status = ?'
        args.append(status_filter)
    if category_filter:
        ticket_query += ' AND t.category_id = ?'
        args.append(category_filter)
    if search_query:
        ticket_query += ' AND (u.name LIKE ? OR CAST(t.ticket_id AS TEXT) LIKE ? OR t.title LIKE ?)'
        like = f'%{search_query}%'
        args.extend([like, like, like])
    ticket_query += ' ORDER BY t.created_at DESC'

    tickets    = query_db(ticket_query, args)
    ec_query = (
        'SELECT ec.*, m.module_code, m.title as module_title, u.name as student_name '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'LEFT JOIN users u ON ec.student_id = u.user_id '
        'WHERE ec.is_draft = 0'
    )
    ec_args = []
    if ec_status_filter:
        ec_query += ' AND ec.status = ?'
        ec_args.append(ec_status_filter)
    if ec_search_query:
        ec_query += ' AND (u.name LIKE ? OR m.module_code LIKE ? OR CAST(ec.ec_id AS TEXT) LIKE ?)'
        like = f'%{ec_search_query}%'
        ec_args.extend([like, like, like])
    ec_query += ' ORDER BY ec.created_at DESC'

    ecs        = query_db(ec_query, ec_args)
    categories = query_db('SELECT * FROM categories')

    return render_template('sst/dashboard.html',
                           tickets=tickets, ecs=ecs, categories=categories,
                           status_filter=status_filter, category_filter=category_filter,
                           search_query=search_query,
                           ec_status_filter=ec_status_filter, ec_search_query=ec_search_query)


@app.route('/sst/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@role_required('sst_admin')
def sst_manage_ticket(ticket_id):
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status  = request.form.get('new_status')
            resolution  = request.form.get('resolution', '').strip()
            notes       = request.form.get('notes', '').strip()
            old_ticket  = query_db('SELECT status FROM support_tickets WHERE ticket_id = ?', (ticket_id,), one=True)

            if new_status in ('Resolved', 'Closed') and not resolution:
                flash('Please provide a resolution description.', 'danger')
            else:
                execute_db('UPDATE support_tickets SET status = ? WHERE ticket_id = ?', (new_status, ticket_id))
                if resolution:
                    execute_db(
                        'UPDATE support_tickets SET resolution = ?, resolved_at = ? WHERE ticket_id = ?',
                        (resolution, datetime.now().isoformat(), ticket_id)
                    )
                execute_db(
                    'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, notes, changed_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', old_ticket['status'], new_status,
                     session['user_id'], notes or None, datetime.now().isoformat())
                )
                flash(f'Status updated to {new_status}. The student will be notified.', 'success')

        elif action == 'add_comment':
            content    = request.form.get('comment', '').strip()
            visibility = request.form.get('visibility', 'public')
            if content:
                execute_db(
                    'INSERT INTO comments (case_id, case_type, author_id, content, visibility, created_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', session['user_id'], content, visibility, datetime.now().isoformat())
                )
                flash('Comment added.', 'success')

        elif action == 'reassign':
            new_team_id   = request.form.get('new_team_id')
            reassign_note = request.form.get('reassign_note', '').strip()

            if not new_team_id:
                flash('Please select a department to reassign to.', 'warning')
            else:
                team = query_db('SELECT name FROM teams WHERE team_id = ?', (new_team_id,), one=True)
                existing = query_db(
                    "SELECT assignment_id FROM assignments WHERE case_id = ? AND case_type = 'ticket'",
                    (ticket_id,), one=True
                )
                if existing:
                    execute_db(
                        'UPDATE assignments SET team_id = ?, assigned_user_id = NULL, assigned_at = ? '
                        'WHERE case_id = ? AND case_type = ?',
                        (new_team_id, datetime.now().isoformat(), ticket_id, 'ticket')
                    )
                else:
                    execute_db(
                        'INSERT INTO assignments (case_id, case_type, team_id, assigned_user_id, assigned_at) '
                        'VALUES (?, ?, ?, NULL, ?)',
                        (ticket_id, 'ticket', new_team_id, datetime.now().isoformat())
                    )
                team_name = team['name'] if team else new_team_id
                note_text = (reassign_note + ' | ' if reassign_note else '') + f'Passed to {team_name}'
                old_ticket = query_db('SELECT status FROM support_tickets WHERE ticket_id = ?', (ticket_id,), one=True)
                execute_db(
                    'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, notes, changed_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', old_ticket['status'], old_ticket['status'],
                     session['user_id'], f'[Reassigned] {note_text}', datetime.now().isoformat())
                )
                flash(f'Ticket reassigned to {team_name}.', 'success')

        elif action == 'add_file':
            files = request.files.getlist('files')
            saved = 0
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"ticket_{ticket_id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    execute_db(
                        'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (ticket_id, 'ticket', file.filename, filename, datetime.now().isoformat())
                    )
                    saved += 1
            flash(f'{saved} file(s) uploaded.', 'success')

        return redirect(url_for('sst_manage_ticket', ticket_id=ticket_id))

    ticket = query_db(
        'SELECT t.*, c.name as category_name, u.name as creator_name, u.email as creator_email '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'WHERE t.ticket_id = ?',
        (ticket_id,), one=True
    )
    if not ticket:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('sst_dashboard'))

    assignment = query_db(
        'SELECT a.*, t.name as team_name, u.name as assigned_user_name '
        'FROM assignments a '
        'LEFT JOIN teams t ON a.team_id = t.team_id '
        'LEFT JOIN users u ON a.assigned_user_id = u.user_id '
        "WHERE a.case_id = ? AND a.case_type = 'ticket'",
        (ticket_id,), one=True
    )
    comments   = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ticket_id, 'ticket')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ticket_id, 'ticket'))
    history     = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ticket_id, 'ticket')
    )
    teams = query_db('SELECT * FROM teams')

    return render_template('sst/manage_ticket.html',
                           ticket=ticket, assignment=assignment,
                           comments=comments, attachments=attachments,
                           history=history, teams=teams)


@app.route('/sst/ec/<int:ec_id>', methods=['GET', 'POST'])
@login_required
@role_required('sst_admin')
def sst_review_ec(ec_id):
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status     = request.form.get('new_status')
            decision_notes = request.form.get('decision_notes', '').strip()
            old_ec         = query_db('SELECT status FROM ec_applications WHERE ec_id = ?', (ec_id,), one=True)

            execute_db(
                'UPDATE ec_applications SET status = ?, decision_notes = ?, decision_date = ? WHERE ec_id = ?',
                (new_status, decision_notes or None, datetime.now().isoformat(), ec_id)
            )
            execute_db(
                'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, notes, changed_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (ec_id, 'ec', old_ec['status'], new_status, session['user_id'],
                 decision_notes or None, datetime.now().isoformat())
            )
            flash(f'EC status updated to {new_status}. The student will be notified.', 'success')

        elif action == 'add_comment':
            content    = request.form.get('comment', '').strip()
            visibility = request.form.get('visibility', 'public')
            if content:
                execute_db(
                    'INSERT INTO comments (case_id, case_type, author_id, content, visibility, created_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ec_id, 'ec', session['user_id'], content, visibility, datetime.now().isoformat())
                )
                flash('Comment added.', 'success')

        elif action == 'add_file':
            files = request.files.getlist('files')
            saved = 0
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"ec_{ec_id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    execute_db(
                        'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (ec_id, 'ec', file.filename, filename, datetime.now().isoformat())
                    )
                    saved += 1
            flash(f'{saved} file(s) uploaded.', 'success')

        return redirect(url_for('sst_review_ec', ec_id=ec_id))

    ec = query_db(
        'SELECT ec.*, m.module_code, m.title as module_title, '
        'a.name as assessment_name, a.due_date as assessment_due, '
        'u.name as student_name, u.email as student_email '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'LEFT JOIN assessments a ON ec.assessment_id = a.assessment_id '
        'LEFT JOIN users u ON ec.student_id = u.user_id '
        'WHERE ec.ec_id = ?',
        (ec_id,), one=True
    )
    if not ec:
        flash('EC application not found.', 'danger')
        return redirect(url_for('sst_dashboard'))

    comments    = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ec_id, 'ec')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ec_id, 'ec'))
    history     = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ec_id, 'ec')
    )

    return render_template('sst/review_ec.html',
                           ec=ec, comments=comments, attachments=attachments, history=history)


@app.route('/sst/tickets')
@login_required
@role_required('sst_admin')
def sst_tickets():
    status_filter   = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    search_query    = request.args.get('search', '').strip()

    query = (
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'JOIN assignments a ON a.case_id = t.ticket_id AND a.case_type = ? '
        'JOIN teams tm ON a.team_id = tm.team_id '
        "WHERE tm.team_type = 'SST'"
    )
    args = ['ticket']
    if status_filter:
        query += ' AND t.status = ?'
        args.append(status_filter)
    if category_filter:
        query += ' AND t.category_id = ?'
        args.append(category_filter)
    if search_query:
        query += ' AND (u.name LIKE ? OR CAST(t.ticket_id AS TEXT) LIKE ? OR t.title LIKE ?)'
        like = f'%{search_query}%'
        args.extend([like, like, like])
    query += ' ORDER BY t.created_at DESC'

    tickets    = query_db(query, args)
    categories = query_db('SELECT * FROM categories')
    return render_template('sst/tickets.html',
                           tickets=tickets, categories=categories,
                           status_filter=status_filter,
                           category_filter=category_filter,
                           search_query=search_query)


@app.route('/sst/ecs')
@login_required
@role_required('sst_admin')
def sst_ecs():
    ec_status_filter = request.args.get('ec_status', '')
    ec_search_query  = request.args.get('ec_search', '').strip()

    ec_query = (
        'SELECT ec.*, m.module_code, m.title as module_title, u.name as student_name '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'LEFT JOIN users u ON ec.student_id = u.user_id '
        'WHERE ec.is_draft = 0'
    )
    ec_args = []
    if ec_status_filter:
        ec_query += ' AND ec.status = ?'
        ec_args.append(ec_status_filter)
    if ec_search_query:
        ec_query += ' AND (u.name LIKE ? OR m.module_code LIKE ? OR CAST(ec.ec_id AS TEXT) LIKE ?)'
        like = f'%{ec_search_query}%'
        ec_args.extend([like, like, like])
    ec_query += ' ORDER BY ec.created_at DESC'

    ecs = query_db(ec_query, ec_args)
    return render_template('sst/ecs.html',
                           ecs=ecs,
                           ec_status_filter=ec_status_filter,
                           ec_search_query=ec_search_query)


@app.route('/sst/reports')
@login_required
@role_required('sst_admin')
def sst_reports():
    ticket_stats = query_db(
        'SELECT c.name as category, t.status, COUNT(*) as count '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'GROUP BY c.name, t.status ORDER BY c.name'
    )
    ec_stats = query_db(
        'SELECT m.module_code, ec.status, COUNT(*) as count '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'WHERE ec.is_draft = 0 '
        'GROUP BY m.module_code, ec.status ORDER BY m.module_code'
    )
    # High-level totals
    total_tickets    = query_db('SELECT COUNT(*) as n FROM support_tickets', one=True)['n']
    open_tickets     = query_db("SELECT COUNT(*) as n FROM support_tickets WHERE status = 'Open'", one=True)['n']
    resolved_tickets = query_db("SELECT COUNT(*) as n FROM support_tickets WHERE status IN ('Resolved','Closed')", one=True)['n']
    total_ecs        = query_db('SELECT COUNT(*) as n FROM ec_applications WHERE is_draft = 0', one=True)['n']

    # Average resolution time per category (tickets resolved/closed with a resolved_at timestamp)
    avg_resolution = query_db(
        "SELECT c.name as category, "
        "ROUND(AVG((julianday(t.resolved_at) - julianday(t.created_at)) * 24), 1) as avg_hours, "
        "COUNT(*) as resolved_count "
        "FROM support_tickets t "
        "LEFT JOIN categories c ON t.category_id = c.category_id "
        "WHERE t.resolved_at IS NOT NULL AND t.status IN ('Resolved', 'Closed') "
        "GROUP BY t.category_id ORDER BY avg_hours"
    )

    return render_template('sst/reports.html',
                           ticket_stats=ticket_stats, ec_stats=ec_stats,
                           total_tickets=total_tickets, open_tickets=open_tickets,
                           resolved_tickets=resolved_tickets, total_ecs=total_ecs,
                           avg_resolution=avg_resolution)


# ──────────────────────────────────────────────
# ITS STAFF ROUTES
# ──────────────────────────────────────────────

@app.route('/its/dashboard')
@login_required
@role_required('its_staff')
def its_dashboard():
    status_filter = request.args.get('status', '')
    search_query  = request.args.get('search', '').strip()

    query = (
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'JOIN assignments a ON a.case_id = t.ticket_id AND a.case_type = ? '
        'JOIN teams tm ON a.team_id = tm.team_id '
        "WHERE tm.team_type = 'ITS'"
    )
    args = ['ticket']
    if status_filter:
        query += ' AND t.status = ?'
        args.append(status_filter)
    if search_query:
        query += ' AND (u.name LIKE ? OR CAST(t.ticket_id AS TEXT) LIKE ? OR t.title LIKE ?)'
        like = f'%{search_query}%'
        args.extend([like, like, like])
    query += ' ORDER BY t.created_at DESC'

    tickets = query_db(query, args)

    # Department stats
    stats = query_db(
        "SELECT t.status, COUNT(*) as count FROM support_tickets t "
        "JOIN assignments a ON a.case_id = t.ticket_id AND a.case_type = 'ticket' "
        "JOIN teams tm ON a.team_id = tm.team_id "
        "WHERE tm.team_type = 'ITS' GROUP BY t.status"
    )
    return render_template('its/dashboard.html', tickets=tickets, status_filter=status_filter,
                           search_query=search_query, stats=stats)


@app.route('/its/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@role_required('its_staff')
def its_manage_ticket(ticket_id):
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status = request.form.get('new_status')
            resolution = request.form.get('resolution', '').strip()
            notes      = request.form.get('notes', '').strip()
            old_ticket = query_db('SELECT status FROM support_tickets WHERE ticket_id = ?', (ticket_id,), one=True)

            if new_status in ('Resolved', 'Closed') and not resolution:
                flash('Please provide a resolution description.', 'danger')
            else:
                execute_db('UPDATE support_tickets SET status = ? WHERE ticket_id = ?', (new_status, ticket_id))
                if resolution:
                    execute_db(
                        'UPDATE support_tickets SET resolution = ?, resolved_at = ? WHERE ticket_id = ?',
                        (resolution, datetime.now().isoformat(), ticket_id)
                    )
                execute_db(
                    'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, notes, changed_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', old_ticket['status'], new_status,
                     session['user_id'], notes or None, datetime.now().isoformat())
                )
                flash(f'Status updated to {new_status}. The student will be notified.', 'success')

        elif action == 'add_comment':
            content = request.form.get('comment', '').strip()
            if content:
                execute_db(
                    'INSERT INTO comments (case_id, case_type, author_id, content, visibility, created_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', session['user_id'], content, 'public', datetime.now().isoformat())
                )
                flash('Comment added.', 'success')

        return redirect(url_for('its_manage_ticket', ticket_id=ticket_id))

    ticket = query_db(
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'WHERE t.ticket_id = ?',
        (ticket_id,), one=True
    )
    comments    = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ticket_id, 'ticket')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ticket_id, 'ticket'))
    history     = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ticket_id, 'ticket')
    )
    return render_template('its/manage_ticket.html',
                           ticket=ticket, comments=comments, attachments=attachments, history=history)


# ──────────────────────────────────────────────
# LAB TECHNICIAN ROUTES
# ──────────────────────────────────────────────

@app.route('/lab/dashboard')
@login_required
@role_required('lab_technician')
def lab_dashboard():
    status_filter = request.args.get('status', '')
    search_query  = request.args.get('search', '').strip()

    query = (
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'JOIN assignments a ON a.case_id = t.ticket_id AND a.case_type = ? '
        'JOIN teams tm ON a.team_id = tm.team_id '
        "WHERE tm.team_type = 'LAB'"
    )
    args = ['ticket']
    if status_filter:
        query += ' AND t.status = ?'
        args.append(status_filter)
    if search_query:
        query += ' AND (u.name LIKE ? OR CAST(t.ticket_id AS TEXT) LIKE ? OR t.title LIKE ?)'
        like = f'%{search_query}%'
        args.extend([like, like, like])
    query += ' ORDER BY t.created_at DESC'

    tickets = query_db(query, args)

    stats = query_db(
        "SELECT t.status, COUNT(*) as count FROM support_tickets t "
        "JOIN assignments a ON a.case_id = t.ticket_id AND a.case_type = 'ticket' "
        "JOIN teams tm ON a.team_id = tm.team_id "
        "WHERE tm.team_type = 'LAB' GROUP BY t.status"
    )
    return render_template('lab/dashboard.html', tickets=tickets, status_filter=status_filter,
                           search_query=search_query, stats=stats)


@app.route('/lab/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@role_required('lab_technician')
def lab_manage_ticket(ticket_id):
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status = request.form.get('new_status')
            resolution = request.form.get('resolution', '').strip()
            notes      = request.form.get('notes', '').strip()
            old_ticket = query_db('SELECT status FROM support_tickets WHERE ticket_id = ?', (ticket_id,), one=True)

            if new_status in ('Resolved', 'Closed') and not resolution:
                flash('Please provide a resolution description.', 'danger')
            else:
                execute_db('UPDATE support_tickets SET status = ? WHERE ticket_id = ?', (new_status, ticket_id))
                if resolution:
                    execute_db(
                        'UPDATE support_tickets SET resolution = ?, resolved_at = ? WHERE ticket_id = ?',
                        (resolution, datetime.now().isoformat(), ticket_id)
                    )
                execute_db(
                    'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, notes, changed_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', old_ticket['status'], new_status,
                     session['user_id'], notes or None, datetime.now().isoformat())
                )
                flash(f'Status updated to {new_status}. The student will be notified.', 'success')

        elif action == 'add_comment':
            content = request.form.get('comment', '').strip()
            if content:
                execute_db(
                    'INSERT INTO comments (case_id, case_type, author_id, content, visibility, created_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', session['user_id'], content, 'public', datetime.now().isoformat())
                )
                flash('Comment added.', 'success')

        return redirect(url_for('lab_manage_ticket', ticket_id=ticket_id))

    ticket = query_db(
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'WHERE t.ticket_id = ?',
        (ticket_id,), one=True
    )
    comments    = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ticket_id, 'ticket')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ticket_id, 'ticket'))
    history     = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ticket_id, 'ticket')
    )
    return render_template('lab/manage_ticket.html',
                           ticket=ticket, comments=comments, attachments=attachments, history=history)


# ──────────────────────────────────────────────
# MODULE ORGANISER ROUTES
# ──────────────────────────────────────────────

@app.route('/organiser/dashboard')
@login_required
@role_required('module_organiser')
def organiser_dashboard():
    organiser_modules = query_db('SELECT * FROM modules WHERE organiser_id = ?', (session['user_id'],))
    module_ids        = [m['module_id'] for m in organiser_modules]
    from_date = request.args.get('from_date', '')
    to_date   = request.args.get('to_date', '')

    ecs = []
    if module_ids:
        placeholders = ','.join('?' * len(module_ids))
        extra_where = ''
        extra_args  = list(module_ids)
        if from_date:
            extra_where += ' AND ec.created_at >= ?'
            extra_args.append(from_date)
        if to_date:
            extra_where += ' AND ec.created_at <= ?'
            extra_args.append(to_date + ' 23:59:59')
        ecs = query_db(
            f'SELECT ec.*, m.module_code, m.title as module_title, '
            f'u.name as student_name, a.name as assessment_name '
            f'FROM ec_applications ec '
            f'LEFT JOIN modules m ON ec.module_id = m.module_id '
            f'LEFT JOIN users u ON ec.student_id = u.user_id '
            f'LEFT JOIN assessments a ON ec.assessment_id = a.assessment_id '
            f'WHERE ec.module_id IN ({placeholders}) AND ec.is_draft = 0{extra_where} '
            f'ORDER BY ec.created_at DESC',
            extra_args
        )

    return render_template('organiser/dashboard.html', ecs=ecs, modules=organiser_modules,
                           from_date=from_date, to_date=to_date)


@app.route('/organiser/ec/<int:ec_id>', methods=['GET', 'POST'])
@login_required
@role_required('module_organiser')
def organiser_view_ec(ec_id):
    """EC detail view for module organisers — read-only with flag action."""
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'flag_sst':
            notes = request.form.get('flag_notes', '').strip()
            content = f'[Flagged by Module Organiser] {notes}' if notes else '[Flagged by Module Organiser for SST review]'
            execute_db(
                'INSERT INTO comments (case_id, case_type, author_id, content, visibility, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (ec_id, 'ec', session['user_id'], content, 'internal', datetime.now().isoformat())
            )
            flash('EC flagged for SST review. The Student Support Team will be notified.', 'success')
            return redirect(url_for('organiser_view_ec', ec_id=ec_id))

    ec = query_db(
        'SELECT ec.*, m.module_code, m.title as module_title, '
        'a.name as assessment_name, a.due_date as assessment_due, '
        'u.name as student_name, u.email as student_email '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'LEFT JOIN assessments a ON ec.assessment_id = a.assessment_id '
        'LEFT JOIN users u ON ec.student_id = u.user_id '
        'WHERE ec.ec_id = ? AND m.organiser_id = ?',
        (ec_id, session['user_id']), one=True
    )
    if not ec:
        flash('EC application not found or access denied.', 'danger')
        return redirect(url_for('organiser_dashboard'))

    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ec_id, 'ec')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ec_id, 'ec'))

    return render_template('organiser/view_ec.html', ec=ec, history=history, attachments=attachments)


# ──────────────────────────────────────────────
# STUDENT — READ-ONLY SERVICES PAGE
# ──────────────────────────────────────────────

@app.route('/student/services')
@login_required
@role_required('student')
def student_services():
    services = query_db('SELECT * FROM service_status ORDER BY name')
    return render_template('student/services.html', services=services)


# ──────────────────────────────────────────────
# SERVICE STATUS — SUGGESTION MODEL
# ──────────────────────────────────────────────

def _submit_service_suggestion(service_id, suggested_status, notes):
    """Helper: inserts a suggestion row for the current user."""
    execute_db(
        'INSERT INTO service_suggestions (service_id, suggested_status, suggested_by, notes, status, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (service_id, suggested_status, session['user_id'], notes or None,
         'pending', datetime.now().isoformat())
    )


@app.route('/sst/services', methods=['GET', 'POST'])
@login_required
@role_required('sst_admin')
def sst_services():
    if request.method == 'POST':
        service_id = int(request.form.get('service_id', 0))
        new_status = request.form.get('status')
        notes      = request.form.get('notes', '').strip()
        if service_id and new_status:
            owned = SERVICE_TEAM_OWNERSHIP.get('SST', [])
            if service_id in owned:
                _submit_service_suggestion(service_id, new_status, notes)
                flash('Suggestion submitted. Awaiting admin approval.', 'info')
            else:
                flash('You can only suggest changes for services managed by SST.', 'warning')
        return redirect(url_for('sst_services'))

    services     = query_db('SELECT * FROM service_status ORDER BY service_type, name')
    sst_services_ids = SERVICE_TEAM_OWNERSHIP.get('SST', [])
    pending = query_db(
        'SELECT ss.*, s.name as service_name FROM service_suggestions ss '
        'JOIN service_status s ON ss.service_id = s.service_id '
        'WHERE ss.suggested_by = ? AND ss.status = ? ORDER BY ss.created_at DESC',
        (session['user_id'], 'pending')
    )
    return render_template('sst/services.html', services=services,
                           owned_ids=sst_services_ids, pending=pending,
                           service_owner=SERVICE_OWNER)


@app.route('/its/services', methods=['GET', 'POST'])
@login_required
@role_required('its_staff')
def its_services():
    if request.method == 'POST':
        service_id = int(request.form.get('service_id', 0))
        new_status = request.form.get('status')
        notes      = request.form.get('notes', '').strip()
        if service_id and new_status:
            owned = SERVICE_TEAM_OWNERSHIP.get('ITS', [])
            if service_id in owned:
                _submit_service_suggestion(service_id, new_status, notes)
                flash('Suggestion submitted. Awaiting admin approval.', 'info')
            else:
                flash('You can only suggest changes for services managed by ITS.', 'warning')
        return redirect(url_for('its_services'))

    services  = query_db('SELECT * FROM service_status ORDER BY service_type, name')
    its_ids   = SERVICE_TEAM_OWNERSHIP.get('ITS', [])
    pending = query_db(
        'SELECT ss.*, s.name as service_name FROM service_suggestions ss '
        'JOIN service_status s ON ss.service_id = s.service_id '
        'WHERE ss.suggested_by = ? AND ss.status = ? ORDER BY ss.created_at DESC',
        (session['user_id'], 'pending')
    )
    return render_template('its/services.html', services=services,
                           owned_ids=its_ids, pending=pending,
                           service_owner=SERVICE_OWNER)


@app.route('/lab/services', methods=['GET', 'POST'])
@login_required
@role_required('lab_technician')
def lab_services():
    if request.method == 'POST':
        service_id = int(request.form.get('service_id', 0))
        new_status = request.form.get('status')
        notes      = request.form.get('notes', '').strip()
        if service_id and new_status:
            owned = SERVICE_TEAM_OWNERSHIP.get('LAB', [])
            if service_id in owned:
                _submit_service_suggestion(service_id, new_status, notes)
                flash('Suggestion submitted. Awaiting admin approval.', 'info')
            else:
                flash('You can only suggest changes for services managed by the Lab team.', 'warning')
        return redirect(url_for('lab_services'))

    services  = query_db('SELECT * FROM service_status ORDER BY service_type, name')
    lab_ids   = SERVICE_TEAM_OWNERSHIP.get('LAB', [])
    pending = query_db(
        'SELECT ss.*, s.name as service_name FROM service_suggestions ss '
        'JOIN service_status s ON ss.service_id = s.service_id '
        'WHERE ss.suggested_by = ? AND ss.status = ? ORDER BY ss.created_at DESC',
        (session['user_id'], 'pending')
    )
    return render_template('lab/services.html', services=services,
                           owned_ids=lab_ids, pending=pending,
                           service_owner=SERVICE_OWNER)


# ──────────────────────────────────────────────
# ADMIN ROUTES
# ──────────────────────────────────────────────

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    users = query_db('SELECT * FROM users ORDER BY role, name')
    return render_template('admin/dashboard.html', users=users)


@app.route('/admin/add-user', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_user():
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role     = request.form.get('role', '').strip()
        year_group = request.form.get('year_group', '').strip() or None

        if not name or not email or not password or not role:
            flash('Please fill in all required fields.', 'danger')
            return render_template('admin/add_user.html')

        existing = query_db('SELECT * FROM users WHERE email = ?', (email,), one=True)
        if existing:
            flash('A user with that email already exists.', 'danger')
            return render_template('admin/add_user.html')

        execute_db(
            'INSERT INTO users (email, password, name, role, year_group) VALUES (?, ?, ?, ?, ?)',
            (email, password, name, role, year_group)
        )
        flash(f'User {name} added successfully.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/add_user.html')


@app.route('/admin/edit-user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    user = query_db('SELECT * FROM users WHERE user_id = ?', (user_id,), one=True)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        name       = request.form.get('name', '').strip()
        email      = request.form.get('email', '').strip()
        role       = request.form.get('role', '').strip()
        year_group = request.form.get('year_group', '').strip() or None
        new_pw     = request.form.get('password', '').strip()

        if not name or not email or not role:
            flash('Name, email and role are required.', 'danger')
            return render_template('admin/edit_user.html', user=user)

        # Check email uniqueness (exclude current user)
        clash = query_db('SELECT user_id FROM users WHERE email = ? AND user_id != ?', (email, user_id), one=True)
        if clash:
            flash('That email is already used by another account.', 'danger')
            return render_template('admin/edit_user.html', user=user)

        if new_pw:
            execute_db(
                'UPDATE users SET name=?, email=?, role=?, year_group=?, password=? WHERE user_id=?',
                (name, email, role, year_group, new_pw, user_id)
            )
        else:
            execute_db(
                'UPDATE users SET name=?, email=?, role=?, year_group=? WHERE user_id=?',
                (name, email, role, year_group, user_id)
            )
        flash(f'{name}\'s account updated.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/edit_user.html', user=user)


@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_user(user_id):
    if user_id == session['user_id']:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin_dashboard'))
    user = query_db('SELECT * FROM users WHERE user_id = ?', (user_id,), one=True)
    if user:
        # Delete all records referencing this user to satisfy FK constraints
        # Comments authored by the user
        execute_db('DELETE FROM comments WHERE author_id = ?', (user_id,))
        # Status changes made by the user
        execute_db('DELETE FROM status_changes WHERE changed_by = ?', (user_id,))
        # Service suggestions made or reviewed by the user
        execute_db('DELETE FROM service_suggestions WHERE suggested_by = ? OR reviewed_by = ?', (user_id, user_id))
        # Assignments where user is assigned staff
        execute_db('DELETE FROM assignments WHERE assigned_user_id = ?', (user_id,))
        # Tickets created by the user (also remove their attachments and status history)
        tickets = query_db('SELECT ticket_id FROM support_tickets WHERE creator_id = ?', (user_id,))
        for t in tickets:
            tid = t['ticket_id']
            execute_db('DELETE FROM attachments WHERE case_id = ? AND case_type = ?', (tid, 'ticket'))
            execute_db('DELETE FROM status_changes WHERE case_id = ? AND case_type = ?', (tid, 'ticket'))
            execute_db('DELETE FROM comments WHERE case_id = ? AND case_type = ?', (tid, 'ticket'))
            execute_db('DELETE FROM assignments WHERE case_id = ? AND case_type = ?', (tid, 'ticket'))
        execute_db('DELETE FROM support_tickets WHERE creator_id = ?', (user_id,))
        # EC applications by the user (also remove their attachments and status history)
        ecs = query_db('SELECT ec_id FROM ec_applications WHERE student_id = ?', (user_id,))
        for e in ecs:
            eid = e['ec_id']
            execute_db('DELETE FROM attachments WHERE case_id = ? AND case_type = ?', (eid, 'ec'))
            execute_db('DELETE FROM status_changes WHERE case_id = ? AND case_type = ?', (eid, 'ec'))
            execute_db('DELETE FROM comments WHERE case_id = ? AND case_type = ?', (eid, 'ec'))
        execute_db('DELETE FROM ec_applications WHERE student_id = ?', (user_id,))
        # Enrollments
        execute_db('DELETE FROM enrollments WHERE student_id = ?', (user_id,))
        # Modules where user is the organiser (set organiser to null rather than deleting)
        execute_db('UPDATE modules SET organiser_id = NULL WHERE organiser_id = ?', (user_id,))
        # Finally delete the user
        execute_db('DELETE FROM users WHERE user_id = ?', (user_id,))
        flash(f'User {user["name"]} and all associated records deleted.', 'warning')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/services', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_services():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'direct_update':
            service_id = request.form.get('service_id')
            new_status = request.form.get('status')
            if service_id and new_status:
                execute_db(
                    'UPDATE service_status SET status = ?, last_updated = ? WHERE service_id = ?',
                    (new_status, datetime.now().isoformat(), service_id)
                )
                flash('Service status updated directly.', 'success')

        elif action == 'approve':
            suggestion_id = request.form.get('suggestion_id')
            review_notes  = request.form.get('review_notes', '').strip()
            sugg = query_db('SELECT * FROM service_suggestions WHERE suggestion_id = ?', (suggestion_id,), one=True)
            if sugg and sugg['status'] == 'pending':
                execute_db(
                    'UPDATE service_status SET status = ?, last_updated = ? WHERE service_id = ?',
                    (sugg['suggested_status'], datetime.now().isoformat(), sugg['service_id'])
                )
                execute_db(
                    'UPDATE service_suggestions SET status=?, reviewed_by=?, reviewed_at=?, review_notes=? '
                    'WHERE suggestion_id=?',
                    ('approved', session['user_id'], datetime.now().isoformat(), review_notes or None, suggestion_id)
                )
                flash('Suggestion approved and service status updated.', 'success')

        elif action == 'reject':
            suggestion_id = request.form.get('suggestion_id')
            review_notes  = request.form.get('review_notes', '').strip()
            execute_db(
                'UPDATE service_suggestions SET status=?, reviewed_by=?, reviewed_at=?, review_notes=? '
                'WHERE suggestion_id=?',
                ('rejected', session['user_id'], datetime.now().isoformat(), review_notes or None, suggestion_id)
            )
            flash('Suggestion rejected.', 'warning')

        return redirect(url_for('admin_services'))

    services    = query_db('SELECT * FROM service_status ORDER BY service_type, name')
    suggestions = query_db(
        'SELECT ss.*, s.name as service_name, u.name as suggested_by_name, u.role as suggested_by_role '
        'FROM service_suggestions ss '
        'JOIN service_status s ON ss.service_id = s.service_id '
        'JOIN users u ON ss.suggested_by = u.user_id '
        'ORDER BY ss.status ASC, ss.created_at DESC'
    )
    pending_count = sum(1 for s in suggestions if s['status'] == 'pending')
    return render_template('admin/services.html', services=services,
                           suggestions=suggestions, pending_count=pending_count,
                           service_owner=SERVICE_OWNER)


# AJAX: staff members for a given team (used by reassign form)
@app.route('/api/team/<int:team_id>/staff')
@login_required
def api_team_staff(team_id):
    from flask import jsonify
    team = query_db('SELECT team_type FROM teams WHERE team_id = ?', (team_id,), one=True)
    if not team:
        return jsonify([])
    role_map = {'SST': 'sst_admin', 'ITS': 'its_staff', 'LAB': 'lab_technician'}
    role = role_map.get(team['team_type'], '')
    if not role:
        return jsonify([])
    staff = query_db('SELECT user_id, name, role FROM users WHERE role = ? ORDER BY name', (role,))
    return jsonify([{'user_id': s['user_id'], 'name': s['name'], 'role': s['role']} for s in staff])


# ──────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)
