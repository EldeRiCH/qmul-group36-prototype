# QMUL Issues & Feedback System - Group 36 Prototype

## Setup (takes 30 seconds)

1. Install Flask:
   pip install flask

2. Create the database:
   python setup_db.py

3. Run the app:
   python app.py

4. Open browser: http://127.0.0.1:5000


## Demo Accounts

  Student:           student@qmul.ac.uk      / password
  Student 2:         student2@qmul.ac.uk     / password
  SST Admin:         sst@qmul.ac.uk          / password
  ITS Staff:         its@qmul.ac.uk          / password
  Lab Technician:    lab@qmul.ac.uk          / password
  Module Organiser:  organiser@qmul.ac.uk    / password


## Project Structure

  app.py                  - Main Flask application (all routes)
  setup_db.py             - Database setup + seed data
  database.db             - SQLite database (created by setup_db.py)
  static/css/style.css    - Custom styles
  static/uploads/         - Uploaded files go here
  templates/
    base.html             - Shared layout (navbar, footer, Bootstrap)
    login.html            - Login page
    student/              - Student pages (dashboard, submit ticket, submit EC, view pages)
    sst/                  - SST Admin pages (dashboard, manage ticket, review EC, reports)
    its/                  - ITS Staff pages (dashboard, manage ticket)
    lab/                  - Lab Technician pages (dashboard, manage ticket)
    organiser/            - Module Organiser pages (EC outcomes view)


## Who works on what

  Role 1 (Lead):        app.py structure, base.html, merging everything
  Role 2 (Auth):        login.html, setup_db.py, auth routes in app.py
  Role 3 (Student):     templates/student/ folder + student routes in app.py
  Role 4 (SST Admin):   templates/sst/ folder + SST routes in app.py
  Role 5 (ITS/Lab):     templates/its/ + templates/lab/ + templates/organiser/ + those routes
  Role 6 (Testing):     Acceptance test document
  Role 7 (Presentation): Demo script + rehearsals
