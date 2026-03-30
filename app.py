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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}

DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')


# ──────────────────────────────────────────────
# DATABASE HELPERS
# ──────────────────────────────────────────────

def get_db():
    """Get database connection for current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row  # Access columns by name
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close database connection when request ends."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    """Run a SELECT query and return results."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    """Run an INSERT/UPDATE/DELETE query and return lastrowid."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ──────────────────────────────────────────────
# AUTH DECORATORS
# ──────────────────────────────────────────────

def login_required(f):
    """Redirect to login if not authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """Restrict access to specific roles."""
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
# CONTEXT PROCESSOR - makes user info available in all templates
# ──────────────────────────────────────────────

@app.context_processor
def inject_user():
    """Make current user info available in every template."""
    if 'user_id' in session:
        return {
            'current_user_id': session['user_id'],
            'current_user_name': session.get('name', ''),
            'current_user_role': session.get('role', ''),
            'current_user_email': session.get('email', '')
        }
    return {}


# ──────────────────────────────────────────────
# AUTH ROUTES (Role 2)
# ──────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('login.html')

        user = query_db(
            'SELECT * FROM users WHERE email = ? AND password = ?',
            (email, password), one=True
        )

        if user:
            session['user_id'] = user['user_id']
            session['name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
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
    """Route to the correct dashboard based on user role."""
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
    else:
        flash('Your role is not recognised. Please contact support.', 'danger')
        return redirect(url_for('logout'))


# ──────────────────────────────────────────────
# STUDENT ROUTES (Role 3)
# ──────────────────────────────────────────────

@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    """Student home: list of their tickets and EC applications."""
    tickets = query_db(
        'SELECT * FROM support_tickets WHERE creator_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    )
    ecs = query_db(
        'SELECT ec.*, m.title as module_title, m.module_code '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'WHERE ec.student_id = ? ORDER BY ec.created_at DESC',
        (session['user_id'],)
    )
    return render_template('student/dashboard.html', tickets=tickets, ecs=ecs)


@app.route('/student/submit-ticket', methods=['GET', 'POST'])
@login_required
@role_required('student')
def submit_ticket():
    """Student submits a new support ticket."""
    categories = query_db('SELECT * FROM categories')

    if request.method == 'POST':
        category_id = request.form.get('category_id')
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()

        # Validation
        if not category_id or not title or not description:
            flash('Please fill in all required fields.', 'danger')
            return render_template('student/submit_ticket.html', categories=categories)

        # Create ticket
        ticket_id = execute_db(
            'INSERT INTO support_tickets (creator_id, category_id, title, description, status, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (session['user_id'], category_id, title, description, 'New', datetime.now().isoformat())
        )

        # Auto-assign to team based on category
        category = query_db('SELECT * FROM categories WHERE category_id = ?', (category_id,), one=True)
        if category:
            execute_db(
                'INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
                (ticket_id, 'ticket', category['default_team_id'], datetime.now().isoformat())
            )

        # Handle file upload
        if 'evidence' in request.files:
            file = request.files['evidence']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"ticket_{ticket_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                execute_db(
                    'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', file.filename, filename, datetime.now().isoformat())
                )

        # Log status change
        execute_db(
            'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (ticket_id, 'ticket', None, 'New', session['user_id'], datetime.now().isoformat())
        )

        flash(f'Ticket #{ticket_id} submitted successfully!', 'success')
        return redirect(url_for('student_dashboard'))

    return render_template('student/submit_ticket.html', categories=categories)


@app.route('/student/submit-ec', methods=['GET', 'POST'])
@login_required
@role_required('student')
def submit_ec():
    """Student submits an EC application."""
    modules = query_db('SELECT * FROM modules ORDER BY module_code')
    assessments = query_db('SELECT * FROM assessments ORDER BY name')

    if request.method == 'POST':
        module_id = request.form.get('module_id')
        assessment_id = request.form.get('assessment_id')
        year_group = request.form.get('year_group', '').strip()
        reason = request.form.get('reason', '').strip()
        description = request.form.get('description', '').strip()

        # Validation
        if not module_id or not assessment_id or not reason or not description:
            flash('Please fill in all required fields.', 'danger')
            return render_template('student/submit_ec.html', modules=modules, assessments=assessments)

        # Create EC application
        ec_id = execute_db(
            'INSERT INTO ec_applications (student_id, module_id, assessment_id, year_group, reason, description, status, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (session['user_id'], module_id, assessment_id, year_group, reason, description, 'Submitted', datetime.now().isoformat())
        )

        # Auto-assign to SST team
        sst_team = query_db('SELECT team_id FROM teams WHERE name = ?', ('Student Support Team',), one=True)
        if sst_team:
            execute_db(
                'INSERT INTO assignments (case_id, case_type, team_id, assigned_at) VALUES (?, ?, ?, ?)',
                (ec_id, 'ec', sst_team['team_id'], datetime.now().isoformat())
            )

        # Handle evidence upload
        if 'evidence' in request.files:
            file = request.files['evidence']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"ec_{ec_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                execute_db(
                    'INSERT INTO attachments (case_id, case_type, file_name, file_path, uploaded_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (ec_id, 'ec', file.filename, filename, datetime.now().isoformat())
                )

        # Log status
        execute_db(
            'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (ec_id, 'ec', None, 'Submitted', session['user_id'], datetime.now().isoformat())
        )

        flash(f'EC Application #{ec_id} submitted successfully!', 'success')
        return redirect(url_for('student_dashboard'))

    return render_template('student/submit_ec.html', modules=modules, assessments=assessments)


@app.route('/student/ticket/<int:ticket_id>')
@login_required
@role_required('student')
def student_view_ticket(ticket_id):
    """Student views a specific ticket's details and history."""
    ticket = query_db(
        'SELECT t.*, c.name as category_name FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'WHERE t.ticket_id = ? AND t.creator_id = ?',
        (ticket_id, session['user_id']), one=True
    )
    if not ticket:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('student_dashboard'))

    comments = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ticket_id, 'ticket')
    )
    attachments = query_db(
        'SELECT * FROM attachments WHERE case_id = ? AND case_type = ?',
        (ticket_id, 'ticket')
    )
    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ticket_id, 'ticket')
    )
    return render_template('student/view_ticket.html',
                           ticket=ticket, comments=comments,
                           attachments=attachments, history=history)


@app.route('/student/ec/<int:ec_id>')
@login_required
@role_required('student')
def student_view_ec(ec_id):
    """Student views a specific EC application."""
    ec = query_db(
        'SELECT ec.*, m.title as module_title, m.module_code, a.name as assessment_name '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'LEFT JOIN assessments a ON ec.assessment_id = a.assessment_id '
        'WHERE ec.ec_id = ? AND ec.student_id = ?',
        (ec_id, session['user_id']), one=True
    )
    if not ec:
        flash('EC application not found.', 'danger')
        return redirect(url_for('student_dashboard'))

    comments = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? AND cm.visibility = ? ORDER BY cm.created_at ASC',
        (ec_id, 'ec', 'public')
    )
    attachments = query_db(
        'SELECT * FROM attachments WHERE case_id = ? AND case_type = ?',
        (ec_id, 'ec')
    )
    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ec_id, 'ec')
    )
    return render_template('student/view_ec.html',
                           ec=ec, comments=comments,
                           attachments=attachments, history=history)


# ──────────────────────────────────────────────
# SST ADMIN ROUTES (Role 4)
# ──────────────────────────────────────────────

@app.route('/sst/dashboard')
@login_required
@role_required('sst_admin')
def sst_dashboard():
    """SST Admin home: all tickets and EC applications."""
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')

    # Build ticket query with optional filters
    ticket_query = (
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id WHERE 1=1'
    )
    ticket_args = []
    if status_filter:
        ticket_query += ' AND t.status = ?'
        ticket_args.append(status_filter)
    if category_filter:
        ticket_query += ' AND t.category_id = ?'
        ticket_args.append(category_filter)
    ticket_query += ' ORDER BY t.created_at DESC'

    tickets = query_db(ticket_query, ticket_args)

    # EC applications
    ecs = query_db(
        'SELECT ec.*, m.module_code, m.title as module_title, u.name as student_name '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'LEFT JOIN users u ON ec.student_id = u.user_id '
        'ORDER BY ec.created_at DESC'
    )

    categories = query_db('SELECT * FROM categories')

    return render_template('sst/dashboard.html',
                           tickets=tickets, ecs=ecs, categories=categories,
                           status_filter=status_filter, category_filter=category_filter)


@app.route('/sst/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@role_required('sst_admin')
def sst_manage_ticket(ticket_id):
    """SST Admin manages a support ticket."""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status = request.form.get('new_status')
            resolution = request.form.get('resolution', '').strip()
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
                    'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', old_ticket['status'], new_status, session['user_id'], datetime.now().isoformat())
                )
                flash(f'Ticket status updated to {new_status}.', 'success')

        elif action == 'add_comment':
            content = request.form.get('comment', '').strip()
            visibility = request.form.get('visibility', 'public')
            if content:
                execute_db(
                    'INSERT INTO comments (case_id, case_type, author_id, content, visibility, created_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', session['user_id'], content, visibility, datetime.now().isoformat())
                )
                flash('Comment added.', 'success')

        elif action == 'reassign':
            new_team_id = request.form.get('new_team_id')
            new_category_id = request.form.get('new_category_id')
            if new_team_id:
                execute_db(
                    'UPDATE assignments SET team_id = ?, assigned_at = ? WHERE case_id = ? AND case_type = ?',
                    (new_team_id, datetime.now().isoformat(), ticket_id, 'ticket')
                )
            if new_category_id:
                execute_db('UPDATE support_tickets SET category_id = ? WHERE ticket_id = ?', (new_category_id, ticket_id))
            flash('Ticket reassigned.', 'success')

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

    comments = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ticket_id, 'ticket')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ticket_id, 'ticket'))
    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ticket_id, 'ticket')
    )
    teams = query_db('SELECT * FROM teams')
    categories = query_db('SELECT * FROM categories')

    return render_template('sst/manage_ticket.html',
                           ticket=ticket, comments=comments, attachments=attachments,
                           history=history, teams=teams, categories=categories)


@app.route('/sst/ec/<int:ec_id>', methods=['GET', 'POST'])
@login_required
@role_required('sst_admin')
def sst_review_ec(ec_id):
    """SST Admin reviews an EC application."""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status = request.form.get('new_status')
            decision_notes = request.form.get('decision_notes', '').strip()
            old_ec = query_db('SELECT status FROM ec_applications WHERE ec_id = ?', (ec_id,), one=True)

            execute_db(
                'UPDATE ec_applications SET status = ?, decision_notes = ?, decision_date = ? WHERE ec_id = ?',
                (new_status, decision_notes, datetime.now().isoformat(), ec_id)
            )
            execute_db(
                'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (ec_id, 'ec', old_ec['status'], new_status, session['user_id'], datetime.now().isoformat())
            )
            flash(f'EC status updated to {new_status}.', 'success')

        elif action == 'add_comment':
            content = request.form.get('comment', '').strip()
            visibility = request.form.get('visibility', 'public')
            if content:
                execute_db(
                    'INSERT INTO comments (case_id, case_type, author_id, content, visibility, created_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ec_id, 'ec', session['user_id'], content, visibility, datetime.now().isoformat())
                )
                flash('Comment added.', 'success')

        return redirect(url_for('sst_review_ec', ec_id=ec_id))

    ec = query_db(
        'SELECT ec.*, m.module_code, m.title as module_title, a.name as assessment_name, '
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

    comments = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ec_id, 'ec')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ec_id, 'ec'))
    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ec_id, 'ec')
    )

    return render_template('sst/review_ec.html',
                           ec=ec, comments=comments, attachments=attachments, history=history)


@app.route('/sst/reports')
@login_required
@role_required('sst_admin')
def sst_reports():
    """SST Admin generates reports."""
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
        'GROUP BY m.module_code, ec.status ORDER BY m.module_code'
    )
    return render_template('sst/reports.html', ticket_stats=ticket_stats, ec_stats=ec_stats)


# ──────────────────────────────────────────────
# ITS STAFF ROUTES (Role 5)
# ──────────────────────────────────────────────

@app.route('/its/dashboard')
@login_required
@role_required('its_staff')
def its_dashboard():
    """ITS staff: only ITL-category tickets."""
    status_filter = request.args.get('status', '')

    query = (
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'WHERE c.name = ?'
    )
    args = ['ITL Issue']
    if status_filter:
        query += ' AND t.status = ?'
        args.append(status_filter)
    query += ' ORDER BY t.created_at DESC'

    tickets = query_db(query, args)
    return render_template('its/dashboard.html', tickets=tickets, status_filter=status_filter)


@app.route('/its/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@role_required('its_staff')
def its_manage_ticket(ticket_id):
    """ITS staff manages an ITL ticket."""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status = request.form.get('new_status')
            resolution = request.form.get('resolution', '').strip()
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
                    'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', old_ticket['status'], new_status, session['user_id'], datetime.now().isoformat())
                )
                flash(f'Ticket status updated to {new_status}.', 'success')

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
    comments = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ticket_id, 'ticket')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ticket_id, 'ticket'))
    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ticket_id, 'ticket')
    )

    return render_template('its/manage_ticket.html',
                           ticket=ticket, comments=comments, attachments=attachments, history=history)


# ──────────────────────────────────────────────
# LAB TECHNICIAN ROUTES (Role 5)
# ──────────────────────────────────────────────

@app.route('/lab/dashboard')
@login_required
@role_required('lab_technician')
def lab_dashboard():
    """Lab technician: only EE Lab-category tickets."""
    status_filter = request.args.get('status', '')

    query = (
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id '
        'WHERE c.name = ?'
    )
    args = ['EE Lab Issue']
    if status_filter:
        query += ' AND t.status = ?'
        args.append(status_filter)
    query += ' ORDER BY t.created_at DESC'

    tickets = query_db(query, args)
    return render_template('lab/dashboard.html', tickets=tickets, status_filter=status_filter)


@app.route('/lab/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@role_required('lab_technician')
def lab_manage_ticket(ticket_id):
    """Lab technician manages an EE Lab ticket."""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_status':
            new_status = request.form.get('new_status')
            resolution = request.form.get('resolution', '').strip()
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
                    'INSERT INTO status_changes (case_id, case_type, old_status, new_status, changed_by, changed_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (ticket_id, 'ticket', old_ticket['status'], new_status, session['user_id'], datetime.now().isoformat())
                )
                flash(f'Ticket status updated to {new_status}.', 'success')

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
    comments = query_db(
        'SELECT cm.*, u.name as author_name FROM comments cm '
        'LEFT JOIN users u ON cm.author_id = u.user_id '
        'WHERE cm.case_id = ? AND cm.case_type = ? ORDER BY cm.created_at ASC',
        (ticket_id, 'ticket')
    )
    attachments = query_db('SELECT * FROM attachments WHERE case_id = ? AND case_type = ?', (ticket_id, 'ticket'))
    history = query_db(
        'SELECT sc.*, u.name as changed_by_name FROM status_changes sc '
        'LEFT JOIN users u ON sc.changed_by = u.user_id '
        'WHERE sc.case_id = ? AND sc.case_type = ? ORDER BY sc.changed_at ASC',
        (ticket_id, 'ticket')
    )

    return render_template('lab/manage_ticket.html',
                           ticket=ticket, comments=comments, attachments=attachments, history=history)


# ──────────────────────────────────────────────
# MODULE ORGANISER ROUTES (Role 5)
# ──────────────────────────────────────────────

@app.route('/organiser/dashboard')
@login_required
@role_required('module_organiser')
def organiser_dashboard():
    """Module organiser: read-only view of EC outcomes for their modules."""
    # Get modules this organiser teaches
    organiser_modules = query_db(
        'SELECT * FROM modules WHERE organiser_id = ?',
        (session['user_id'],)
    )
    module_ids = [m['module_id'] for m in organiser_modules]

    ecs = []
    if module_ids:
        placeholders = ','.join('?' * len(module_ids))
        ecs = query_db(
            f'SELECT ec.*, m.module_code, m.title as module_title, u.name as student_name '
            f'FROM ec_applications ec '
            f'LEFT JOIN modules m ON ec.module_id = m.module_id '
            f'LEFT JOIN users u ON ec.student_id = u.user_id '
            f'WHERE ec.module_id IN ({placeholders}) '
            f'ORDER BY ec.created_at DESC',
            module_ids
        )

    return render_template('organiser/dashboard.html', ecs=ecs, modules=organiser_modules)


# ──────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)
