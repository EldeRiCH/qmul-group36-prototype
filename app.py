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
            session['user_id'] = user['user_id']
            session['name']    = user['name']
            session['email']   = user['email']
            session['role']    = user['role']
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
    return render_template('student/dashboard.html', tickets=tickets, ecs=ecs)


@app.route('/student/submit-ticket', methods=['GET', 'POST'])
@login_required
@role_required('student')
def submit_ticket():
    categories = query_db('SELECT * FROM categories')

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
        year_group    = request.form.get('year_group', '').strip()
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
            sst_team = query_db("SELECT team_id FROM teams WHERE name = 'Student Support Team'", one=True)
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
    sst_team = query_db("SELECT team_id FROM teams WHERE name = 'Student Support Team'", one=True)
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


@app.route('/student/ticket/<int:ticket_id>')
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


@app.route('/student/ec/<int:ec_id>')
@login_required
@role_required('student')
def student_view_ec(ec_id):
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
    status_filter   = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    search_query    = request.args.get('search', '').strip()

    ticket_query = (
        'SELECT t.*, c.name as category_name, u.name as creator_name '
        'FROM support_tickets t '
        'LEFT JOIN categories c ON t.category_id = c.category_id '
        'LEFT JOIN users u ON t.creator_id = u.user_id WHERE 1=1'
    )
    args = []
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
    ecs        = query_db(
        'SELECT ec.*, m.module_code, m.title as module_title, u.name as student_name '
        'FROM ec_applications ec '
        'LEFT JOIN modules m ON ec.module_id = m.module_id '
        'LEFT JOIN users u ON ec.student_id = u.user_id '
        'WHERE ec.is_draft = 0 '
        'ORDER BY ec.created_at DESC'
    )
    categories = query_db('SELECT * FROM categories')

    return render_template('sst/dashboard.html',
                           tickets=tickets, ecs=ecs, categories=categories,
                           status_filter=status_filter, category_filter=category_filter,
                           search_query=search_query)


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
                flash(f'Status updated to {new_status}.', 'success')

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
            new_team_id      = request.form.get('new_team_id')
            new_category_id  = request.form.get('new_category_id')
            new_assigned_uid = request.form.get('assigned_user_id')
            if new_team_id:
                existing = query_db(
                    "SELECT assignment_id FROM assignments WHERE case_id = ? AND case_type = 'ticket'",
                    (ticket_id,), one=True
                )
                if existing:
                    execute_db(
                        'UPDATE assignments SET team_id = ?, assigned_user_id = ?, assigned_at = ? '
                        'WHERE case_id = ? AND case_type = ?',
                        (new_team_id, new_assigned_uid or None,
                         datetime.now().isoformat(), ticket_id, 'ticket')
                    )
                else:
                    execute_db(
                        'INSERT INTO assignments (case_id, case_type, team_id, assigned_user_id, assigned_at) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (ticket_id, 'ticket', new_team_id,
                         new_assigned_uid or None, datetime.now().isoformat())
                    )
            if new_category_id:
                execute_db('UPDATE support_tickets SET category_id = ? WHERE ticket_id = ?',
                           (new_category_id, ticket_id))
            flash('Ticket reassigned.', 'success')

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
    teams       = query_db('SELECT * FROM teams')
    categories  = query_db('SELECT * FROM categories')
    # Staff members that can be assigned (all non-student roles)
    staff_members = query_db(
        "SELECT user_id, name, role FROM users WHERE role != 'student' ORDER BY name"
    )

    return render_template('sst/manage_ticket.html',
                           ticket=ticket, assignment=assignment,
                           comments=comments, attachments=attachments,
                           history=history, teams=teams, categories=categories,
                           staff_members=staff_members)


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
            flash(f'EC status updated to {new_status}.', 'success')

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

    return render_template('sst/reports.html',
                           ticket_stats=ticket_stats, ec_stats=ec_stats,
                           total_tickets=total_tickets, open_tickets=open_tickets,
                           resolved_tickets=resolved_tickets, total_ecs=total_ecs)


# ──────────────────────────────────────────────
# ITS STAFF ROUTES
# ──────────────────────────────────────────────

@app.route('/its/dashboard')
@login_required
@role_required('its_staff')
def its_dashboard():
    status_filter = request.args.get('status', '')

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
    query += ' ORDER BY t.created_at DESC'

    tickets = query_db(query, args)

    # Department stats
    stats = query_db(
        "SELECT t.status, COUNT(*) as count FROM support_tickets t "
        "JOIN assignments a ON a.case_id = t.ticket_id AND a.case_type = 'ticket' "
        "JOIN teams tm ON a.team_id = tm.team_id "
        "WHERE tm.team_type = 'ITS' GROUP BY t.status"
    )
    return render_template('its/dashboard.html', tickets=tickets, status_filter=status_filter, stats=stats)


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
                flash(f'Status updated to {new_status}.', 'success')

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
    query += ' ORDER BY t.created_at DESC'

    tickets = query_db(query, args)

    stats = query_db(
        "SELECT t.status, COUNT(*) as count FROM support_tickets t "
        "JOIN assignments a ON a.case_id = t.ticket_id AND a.case_type = 'ticket' "
        "JOIN teams tm ON a.team_id = tm.team_id "
        "WHERE tm.team_type = 'LAB' GROUP BY t.status"
    )
    return render_template('lab/dashboard.html', tickets=tickets, status_filter=status_filter, stats=stats)


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
                flash(f'Status updated to {new_status}.', 'success')

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

    ecs = []
    if module_ids:
        placeholders = ','.join('?' * len(module_ids))
        ecs = query_db(
            f'SELECT ec.*, m.module_code, m.title as module_title, '
            f'u.name as student_name, a.name as assessment_name '
            f'FROM ec_applications ec '
            f'LEFT JOIN modules m ON ec.module_id = m.module_id '
            f'LEFT JOIN users u ON ec.student_id = u.user_id '
            f'LEFT JOIN assessments a ON ec.assessment_id = a.assessment_id '
            f'WHERE ec.module_id IN ({placeholders}) AND ec.is_draft = 0 '
            f'ORDER BY ec.created_at DESC',
            module_ids
        )

    return render_template('organiser/dashboard.html', ecs=ecs, modules=organiser_modules)


# ──────────────────────────────────────────────
# SERVICE STATUS (SST admin update)
# ──────────────────────────────────────────────

@app.route('/sst/services', methods=['GET', 'POST'])
@login_required
@role_required('sst_admin')
def sst_services():
    if request.method == 'POST':
        service_id = request.form.get('service_id')
        new_status = request.form.get('status')
        if service_id and new_status:
            execute_db(
                'UPDATE service_status SET status = ?, last_updated = ? WHERE service_id = ?',
                (new_status, datetime.now().isoformat(), service_id)
            )
            flash('Service status updated.', 'success')
        return redirect(url_for('sst_services'))

    services = query_db('SELECT * FROM service_status ORDER BY name')
    return render_template('sst/services.html', services=services)

# ──────────────────────────────────────────────
# ADMIN ROUTES
# ──────────────────────────────────────────────

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    users = query_db('SELECT * FROM users ORDER BY role, name')
    return render_template('admin/dashboard.html', users=users)

@app.route('/admin/edit-user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    user = query_db('SELECT * FROM users WHERE user_id = ?', (user_id,), one=True)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip()

        if not name or not email or not role:
            flash('Please fill in all required fields.', 'danger')
            return render_template('admin/edit_user.html', user=user)

        if password:
            execute_db(
                'UPDATE users SET name = ?, email = ?, password = ?, role = ? WHERE user_id = ?',
                (name, email, password, role, user_id)
            )
        else:
            execute_db(
                'UPDATE users SET name = ?, email = ?, role = ? WHERE user_id = ?',
                (name, email, role, user_id)
            )

        flash(f'User {name} updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/edit_user.html', user=user)
@app.route('/admin/add-user', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_user():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip()

        if not name or not email or not password or not role:
            flash('Please fill in all fields.', 'danger')
            return render_template('admin/add_user.html')

        existing = query_db('SELECT * FROM users WHERE email = ?', (email,), one=True)
        if existing:
            flash('A user with that email already exists.', 'danger')
            return render_template('admin/add_user.html')

        execute_db(
            'INSERT INTO users (email, password, name, role) VALUES (?, ?, ?, ?)',
            (email, password, name, role)
        )
        flash(f'User {name} added successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/add_user.html')
# ──────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)
