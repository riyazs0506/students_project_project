# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change_this_secret_in_production"

# ---------- DB config - adjust to your environment ----------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "123456",   # <-- change to your DB password
    "database": "student_management",
    "auth_plugin": "mysql_native_password"
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# ----------------- Helpers -----------------
def fetchall(query, params=()):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def fetchone(query, params=()):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def execute(query, params=()):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close(); conn.close()

# ----------------- Auth & Home -----------------
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET','POST'])
def register():
    # Allows registering Principal or Teacher (but typically Principals will be added)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'Principal')

        if not (name and email and password and role):
            flash("All fields are required.", "danger")
            return redirect(url_for('register'))

        # check email exists
        existing = fetchone("SELECT id FROM users WHERE email=%s", (email,))
        if existing:
            flash("Email already registered.", "danger")
            return redirect(url_for('register'))

        pw_hash = generate_password_hash(password)
        execute("INSERT INTO users (name,email,password,role) VALUES (%s,%s,%s,%s)", (name,email,pw_hash,role))
        flash("Registration successful. Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password_input = request.form.get('password', '').strip()

        user = fetchone("SELECT * FROM users WHERE email=%s", (email,))
        if not user or not check_password_hash(user['password'], password_input):
            flash("Invalid email or password.", "danger")
            return redirect(url_for('login'))

        # set session
        session['user_id'] = user['id']
        session['name'] = user['name']
        session['email'] = user['email']
        session['role'] = user['role']
        flash(f"Welcome {user['name']}", "success")
        if user['role'] == 'Principal':
            return redirect(url_for('principal_dashboard'))
        else:
            return redirect(url_for('teacher_dashboard'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ----------------- Dashboards -----------------
@app.route('/principal_dashboard')
def principal_dashboard():
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Please login as Principal.", "danger")
        return redirect(url_for('login'))
    # summary counts
    total_students = fetchone("SELECT COUNT(*) AS c FROM students WHERE principal_id=%s", (session['user_id'],))['c']
    total_teachers = fetchone("SELECT COUNT(*) AS c FROM teachers WHERE principal_id=%s", (session['user_id'],))['c']
    total_subjects = fetchone("SELECT COUNT(*) AS c FROM subjects WHERE principal_id=%s", (session['user_id'],))['c']
    total_marks = fetchone("SELECT COUNT(*) AS c FROM marks WHERE principal_id=%s", (session['user_id'],))['c']
    return render_template('principal_dashboard.html', name=session['name'],
                           students_count=total_students, teachers_count=total_teachers,
                           subjects_count=total_subjects, marks_count=total_marks)

@app.route('/teacher_dashboard')
def teacher_dashboard():
    if 'user_id' not in session or session.get('role') != 'Teacher':
        flash("Please login as Teacher.", "danger")
        return redirect(url_for('login'))
    # teacher sees students assigned to them
    teacher = fetchone("SELECT * FROM teachers WHERE principal_id=%s AND email=%s", (session['user_id'], session['email']))
    students = []
    if teacher:
        students = fetchall("SELECT * FROM students WHERE teacher_id=%s", (teacher['id'],))
    return render_template('teacher_dashboard.html', name=session['name'], students=students)

# ----------------- Students CRUD -----------------
@app.route('/students')
def students_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') == 'Principal':
        students = fetchall("SELECT s.*, t.name AS teacher_name FROM students s LEFT JOIN teachers t ON s.teacher_id=t.id WHERE s.principal_id=%s ORDER BY s.id DESC", (session['user_id'],))
    else:
        # teacher view: show only students assigned to this teacher record (find teacher row by email & principal)
        teacher = fetchone("SELECT * FROM teachers WHERE principal_id=%s AND email=%s", (session['user_id'], session['email']))
        if teacher:
            students = fetchall("SELECT s.*, t.name AS teacher_name FROM students s LEFT JOIN teachers t ON s.teacher_id=t.id WHERE s.teacher_id=%s ORDER BY s.id DESC", (teacher['id'],))
        else:
            students = []
    return render_template('students.html', students=students)

@app.route('/add_student', methods=['GET','POST'])
def add_student():
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can add students.", "danger")
        return redirect(url_for('students_list'))
    teachers = fetchall("SELECT id, name FROM teachers WHERE principal_id=%s ORDER BY name", (session['user_id'],))
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        grade = request.form.get('grade','').strip()
        teacher_id = request.form.get('teacher_id') or None
        if teacher_id == '': teacher_id = None
        if not name:
            flash("Student name required.", "danger")
            return redirect(url_for('add_student'))
        execute("INSERT INTO students (principal_id,name,grade,teacher_id) VALUES (%s,%s,%s,%s)",
                (session['user_id'], name, grade, teacher_id))
        flash("Student added.", "success")
        return redirect(url_for('students_list'))
    return render_template('add_student.html', teachers=teachers)

@app.route('/edit_student/<int:student_id>', methods=['GET','POST'])
def edit_student(student_id):
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can edit students.", "danger")
        return redirect(url_for('students_list'))
    student = fetchone("SELECT * FROM students WHERE id=%s AND principal_id=%s", (student_id, session['user_id']))
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('students_list'))
    teachers = fetchall("SELECT id, name FROM teachers WHERE principal_id=%s ORDER BY name", (session['user_id'],))
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        grade = request.form.get('grade','').strip()
        teacher_id = request.form.get('teacher_id') or None
        if teacher_id == '': teacher_id = None
        if not name:
            flash("Student name required.", "danger")
            return redirect(url_for('edit_student', student_id=student_id))
        execute("UPDATE students SET name=%s, grade=%s, teacher_id=%s WHERE id=%s AND principal_id=%s",
                (name, grade, teacher_id, student_id, session['user_id']))
        flash("Student updated.", "success")
        return redirect(url_for('students_list'))
    return render_template('edit_student.html', student=student, teachers=teachers)

@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can delete students.", "danger")
        return redirect(url_for('students_list'))
    execute("DELETE FROM students WHERE id=%s AND principal_id=%s", (student_id, session['user_id']))
    flash("Student deleted.", "success")
    return redirect(url_for('students_list'))

# ----------------- Teachers CRUD -----------------
@app.route('/teachers')
def teachers_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') == 'Principal':
        teachers = fetchall("SELECT * FROM teachers WHERE principal_id=%s ORDER BY id DESC", (session['user_id'],))
    else:
        teachers = []
    return render_template('teachers.html', teachers=teachers)

@app.route('/add_teacher', methods=['GET','POST'])
def add_teacher():
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can add teachers.", "danger")
        return redirect(url_for('teachers_list'))
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        email = request.form.get('email','').strip()
        phone = request.form.get('phone','').strip()
        if not name:
            flash("Name required.", "danger")
            return redirect(url_for('add_teacher'))
        execute("INSERT INTO teachers (principal_id,name,email,phone) VALUES (%s,%s,%s,%s)", (session['user_id'], name, email, phone))
        flash("Teacher added.", "success")
        return redirect(url_for('teachers_list'))
    return render_template('add_teacher.html')

@app.route('/edit_teacher/<int:teacher_id>', methods=['GET','POST'])
def edit_teacher(teacher_id):
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can edit teachers.", "danger")
        return redirect(url_for('teachers_list'))
    teacher = fetchone("SELECT * FROM teachers WHERE id=%s AND principal_id=%s", (teacher_id, session['user_id']))
    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('teachers_list'))
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        email = request.form.get('email','').strip()
        phone = request.form.get('phone','').strip()
        if not name:
            flash("Name required.", "danger")
            return redirect(url_for('edit_teacher', teacher_id=teacher_id))
        execute("UPDATE teachers SET name=%s, email=%s, phone=%s WHERE id=%s AND principal_id=%s", (name,email,phone,teacher_id,session['user_id']))
        flash("Teacher updated.", "success")
        return redirect(url_for('teachers_list'))
    return render_template('edit_teacher.html', teacher=teacher)

@app.route('/delete_teacher/<int:teacher_id>', methods=['POST'])
def delete_teacher(teacher_id):
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can delete teachers.", "danger")
        return redirect(url_for('teachers_list'))
    execute("DELETE FROM teachers WHERE id=%s AND principal_id=%s", (teacher_id, session['user_id']))
    flash("Teacher deleted.", "success")
    return redirect(url_for('teachers_list'))

# ----------------- Subjects CRUD -----------------
@app.route('/subjects')
def subjects_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') == 'Principal':
        subjects = fetchall("SELECT * FROM subjects WHERE principal_id=%s ORDER BY id DESC", (session['user_id'],))
    else:
        # teacher sees principal's subjects; teacher must belong to principal
        subjects = fetchall("SELECT * FROM subjects WHERE principal_id=%s ORDER BY id DESC", (session['user_id'],))
    return render_template('subjects.html', subjects=subjects)

@app.route('/add_subject', methods=['GET','POST'])
def add_subject():
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can add subjects.", "danger")
        return redirect(url_for('subjects_list'))
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        if not name:
            flash("Subject name required.", "danger")
            return redirect(url_for('add_subject'))
        execute("INSERT INTO subjects (principal_id,name) VALUES (%s,%s)", (session['user_id'], name))
        flash("Subject added.", "success")
        return redirect(url_for('subjects_list'))
    return render_template('add_subject.html')

@app.route('/delete_subject/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can delete subjects.", "danger")
        return redirect(url_for('subjects_list'))
    execute("DELETE FROM subjects WHERE id=%s AND principal_id=%s", (subject_id, session['user_id']))
    flash("Subject deleted.", "success")
    return redirect(url_for('subjects_list'))

# ----------------- Marks -----------------
@app.route('/marks')
def marks_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # principal sees marks for their students
    marks = fetchall("""
        SELECT m.id, m.marks, s.name AS student_name, sub.name AS subject_name, m.student_id
        FROM marks m
        JOIN students s ON m.student_id = s.id
        JOIN subjects sub ON m.subject_id = sub.id
        WHERE m.principal_id=%s
        ORDER BY m.id DESC
    """, (session['user_id'],))
    return render_template('marks.html', marks=marks)

@app.route('/add_marks', methods=['GET','POST'])
def add_marks():
    if 'user_id' not in session or session.get('role') != 'Principal':
        flash("Only Principal can add marks.", "danger")
        return redirect(url_for('marks_list'))
    students = fetchall("SELECT id, name FROM students WHERE principal_id=%s ORDER BY name", (session['user_id'],))
    subjects = fetchall("SELECT id, name FROM subjects WHERE principal_id=%s ORDER BY name", (session['user_id'],))
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        if not student_id:
            flash("Select a student.", "danger")
            return redirect(url_for('add_marks'))
        # For each subject, expect input named marks_<subject_id>
        for sub in subjects:
            value = request.form.get(f"marks_{sub['id']}", "").strip()
            if value == "":
                continue
            try:
                mval = int(value)
            except ValueError:
                mval = 0
            # insert mark record (principal_id stored so queries are scoped)
            execute("INSERT INTO marks (principal_id, student_id, subject_id, marks) VALUES (%s,%s,%s,%s)", (session['user_id'], student_id, sub['id'], mval))
        flash("Marks saved.", "success")
        return redirect(url_for('marks_list'))
    return render_template('add_marks.html', students=students, subjects=subjects)

@app.route('/student_marks/<int:student_id>')
def student_marks(student_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # ensure student belongs to this principal
    student = fetchone("SELECT * FROM students WHERE id=%s AND principal_id=%s", (student_id, session['user_id']))
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('students_list'))
    marks = fetchall("""
        SELECT m.id, m.marks, sub.name AS subject_name
        FROM marks m JOIN subjects sub ON m.subject_id = sub.id
        WHERE m.student_id=%s AND m.principal_id=%s
        ORDER BY m.created_at DESC
    """, (student_id, session['user_id']))
    return render_template('student_marks.html', student=student, marks=marks)

# ----------------- Run -----------------
if __name__ == "__main__":
    app.run(debug=True)

