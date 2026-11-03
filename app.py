
import os
from datetime import date
from io import BytesIO
from functools import wraps

from dotenv import load_dotenv

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, make_response, send_file, session
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from mysql.connector import Error

from database.db import get_connection, get_count
from scheduler.timetable_generator import generate_timetable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)

import hashlib
import secrets
import smtplib
import re

from datetime import datetime, timedelta, date
from email.message import EmailMessage
from functools import wraps

def send_reset_email(recipient, reset_url):
    message = EmailMessage()
    message["Subject"] = "Faculty Timetable Generator - Password Reset"
    message["From"] = os.environ["MAIL_FROM"]
    message["To"] = recipient

    message.set_content(
        "A password reset was requested for your account.\n\n"
        f"Reset your password using this link:\n{reset_url}\n\n"
        "This link expires in 15 minutes and can be used once.\n"
        "If you did not request this, ignore this email."
    )

    host = os.environ.get("MAIL_HOST", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", "587"))
    username = os.environ["MAIL_USERNAME"]
    password = os.environ["MAIL_PASSWORD"]

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.send_message(message)
def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper
def admin_required(route_function):
    @wraps(route_function)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get("role", "").upper() != "ADMIN":
            flash("Access denied! Admin permission is required.", "error")
            return redirect(url_for("dashboard"))

        return route_function(*args, **kwargs)

    return wrapper


# Load environment variables from .env
load_dotenv()

# Initialize Flask
app = Flask(__name__)
@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200

# Configure the session security key
app.secret_key = os.environ.get("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY is missing. Add it to your .env file."
    )

def close_connection(connection, cursor):
    """Close database resources safely."""
    if cursor is not None:
        cursor.close()
    if connection is not None:
        connection.close()
    

# ================= LOGIN ROUTE =================


@app.route("/login", methods=["GET", "POST"])
def login():
    # Always show the login page for GET requests.
    # Only redirect after a successful login.
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Please enter username and password.", "error")
        return redirect(url_for("login"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("login"))

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT user_id, username, password_hash, role
            FROM users
            WHERE username = %s
            """,
            (username,)
        )

        user = cursor.fetchone()

        if user and check_password_hash(
            user["password_hash"], password
        ):
            session.clear()
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            print("LOGIN SESSION:", dict(session))

            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    except Error as error:
        print("Login error:", error)
        flash("Unable to log in. Please try again.", "error")

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

    return redirect(url_for("login"))
@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("login"))


# ============================================================
# HOME AND DASHBOARD
# ============================================================
@app.route("/")
def index():
    """Always open the login page first."""
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    """Display dashboard statistics only after login."""

    # Protect dashboard from logged-out visitors.
    if not session.get("user_id"):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        stats = {
            "faculty_count": get_count("faculty"),
            "subject_count": get_count("subjects"),
            "class_count": get_count("classes"),
            "room_count": get_count("rooms"),
            "department_count": get_count("departments"),
            "time_slot_count": get_count("time_slots"),
            "timetable_count": 0
        }

        connection = get_connection()

        if connection is not None:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM timetable")
            result = cursor.fetchone()

            if result:
                stats["timetable_count"] = result[0]

    except Exception as error:
        print("Dashboard error:", error)

        stats = {
            "faculty_count": 0,
            "subject_count": 0,
            "class_count": 0,
            "room_count": 0,
            "department_count": 0,
            "time_slot_count": 0,
            "timetable_count": 0
        }

    finally:
        if cursor is not None or connection is not None:
            close_connection(connection, cursor)

    return render_template("dashboard.html", **stats)


# ============================================================
# DEPARTMENTS
# ============================================================

@app.route("/departments")
@login_required
def departments():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template(
            "departments.html",
            departments=[]
        )

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                department_id,
                department_name,
                department_code
            FROM departments
            ORDER BY department_id DESC
        """)

        departments_data = cursor.fetchall()

    except Error as error:
        print("Departments loading error:", error)
        departments_data = []
        flash(f"Unable to load departments: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return render_template(
        "departments.html",
        departments=departments_data
    )


# ADMIN ONLY: ADD DEPARTMENT
@app.route("/departments/add", methods=["POST"])
@admin_required
def add_department():
    department_name = request.form.get(
        "department_name", ""
    ).strip()

    department_code = request.form.get(
        "department_code", ""
    ).strip()

    if not department_name:
        flash("Department name is required.", "error")
        return redirect(url_for("departments"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("departments"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO departments (
                department_name,
                department_code
            )
            VALUES (%s, %s)
        """, (
            department_name,
            department_code
        ))

        connection.commit()
        flash("Department added successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Department add error:", error)
        flash(f"Unable to add department: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("departments"))


# ADMIN ONLY: DELETE DEPARTMENT
@app.route("/departments/delete/<int:department_id>")
@admin_required
def delete_department(department_id):
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("departments"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM departments
            WHERE department_id = %s
        """, (department_id,))

        connection.commit()

        if cursor.rowcount > 0:
            flash("Department deleted successfully.", "success")
        else:
            flash("Department not found.", "error")

    except Error as error:
        connection.rollback()
        print("Department delete error:", error)
        flash(f"Unable to delete department: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("departments"))

# ============================================================
# FACULTY
# ============================================================

@app.route("/faculty")
@login_required
def faculty():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template(
            "faculty.html",
            faculty=[],
            departments=[]
        )

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                f.faculty_id,
                f.faculty_name,
                f.employee_id,
                f.email,
                f.phone,
                f.designation,
                f.department_id,
                f.max_classes_per_day,
                d.department_name
            FROM faculty f
            LEFT JOIN departments d
                ON f.department_id = d.department_id
            ORDER BY f.faculty_id DESC
        """)
        faculty_data = cursor.fetchall()

        cursor.execute("""
            SELECT department_id, department_name
            FROM departments
            ORDER BY department_name
        """)
        departments_data = cursor.fetchall()

    except Error as error:
        print("Faculty loading error:", error)
        faculty_data = []
        departments_data = []
        flash(f"Unable to load faculty: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return render_template(
        "faculty.html",
        faculty=faculty_data,
        departments=departments_data
    )


@app.route("/faculty/save", methods=["POST"])
@admin_required
def save_faculty():
    faculty_id = request.form.get("faculty_id", "").strip()
    faculty_name = request.form.get("faculty_name", "").strip()
    employee_id = request.form.get("employee_id", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    designation = request.form.get("designation", "").strip()
    department_id = request.form.get("department_id", "").strip()
    max_classes_per_day = request.form.get(
        "max_classes_per_day", "4"
    ).strip()

    if not faculty_name or not employee_id:
        flash("Faculty name and Employee ID are required.", "error")
        return redirect(url_for("faculty"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("faculty"))

    cursor = connection.cursor()

    try:
        if faculty_id:
            cursor.execute("""
                UPDATE faculty
                SET faculty_name=%s,
                    employee_id=%s,
                    email=%s,
                    phone=%s,
                    designation=%s,
                    department_id=%s,
                    max_classes_per_day=%s
                WHERE faculty_id=%s
            """, (
                faculty_name,
                employee_id,
                email or None,
                phone or None,
                designation or None,
                department_id or None,
                max_classes_per_day or 4,
                faculty_id
            ))
            flash("Faculty updated successfully.", "success")

        else:
            cursor.execute("""
                INSERT INTO faculty (
                    faculty_name, employee_id, email, phone,
                    designation, department_id, max_classes_per_day
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                faculty_name,
                employee_id,
                email or None,
                phone or None,
                designation or None,
                department_id or None,
                max_classes_per_day or 4
            ))
            flash("Faculty added successfully.", "success")

        connection.commit()

    except Error as error:
        connection.rollback()
        print("Faculty save error:", error)
        flash(f"Unable to save faculty: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("faculty"))


@app.route("/faculty/delete/<int:faculty_id>")
@admin_required
def delete_faculty(faculty_id):
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("faculty"))

    cursor = connection.cursor()

    try:
        # Remove related records before deleting faculty.
        cursor.execute(
            "DELETE FROM timetable WHERE faculty_id=%s",
            (faculty_id,)
        )
        cursor.execute(
            "DELETE FROM subject_faculty WHERE faculty_id=%s",
            (faculty_id,)
        )
        cursor.execute(
            "DELETE FROM faculty_availability WHERE faculty_id=%s",
            (faculty_id,)
        )
        cursor.execute(
            "DELETE FROM faculty WHERE faculty_id=%s",
            (faculty_id,)
        )

        connection.commit()
        flash("Faculty deleted successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Faculty delete error:", error)
        flash(f"Unable to delete faculty: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("faculty"))

# ============================================================
# SUBJECTS
# ============================================================

# ADMIN AND STAFF CAN VIEW SUBJECTS
@app.route("/subjects")
@login_required
def subjects():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template(
            "subjects.html",
            subjects=[],
            departments=[]
        )

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                s.subject_id,
                s.subject_name,
                s.subject_code,
                s.subject_type,
                s.weekly_hours,
                s.department_id,
                d.department_name
            FROM subjects s
            LEFT JOIN departments d
                ON s.department_id = d.department_id
            ORDER BY s.subject_id DESC
        """)
        subjects_data = cursor.fetchall()

        cursor.execute("""
            SELECT department_id, department_name
            FROM departments
            ORDER BY department_name
        """)
        departments_data = cursor.fetchall()

    except Error as error:
        print("Subjects loading error:", error)
        subjects_data = []
        departments_data = []
        flash(f"Unable to load subjects: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return render_template(
        "subjects.html",
        subjects=subjects_data,
        departments=departments_data
    )


# ADMIN ONLY: ADD OR EDIT SUBJECT
@app.route("/subjects/save", methods=["POST"])
@admin_required
def save_subject():
    subject_id = request.form.get("subject_id", "").strip()
    subject_name = request.form.get("subject_name", "").strip()
    subject_code = request.form.get("subject_code", "").strip()
    subject_type = request.form.get("subject_type", "Theory").strip()
    weekly_hours = request.form.get("weekly_hours", "1").strip()
    department_id = request.form.get("department_id", "").strip()

    if not subject_name:
        flash("Subject name is required.", "error")
        return redirect(url_for("subjects"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("subjects"))

    cursor = connection.cursor()

    try:
        if subject_id:
            cursor.execute("""
                UPDATE subjects
                SET subject_name=%s,
                    subject_code=%s,
                    subject_type=%s,
                    weekly_hours=%s,
                    department_id=%s
                WHERE subject_id=%s
            """, (
                subject_name,
                subject_code,
                subject_type,
                weekly_hours,
                department_id or None,
                subject_id
            ))
            flash("Subject updated successfully.", "success")

        else:
            cursor.execute("""
                INSERT INTO subjects (
                    subject_name,
                    subject_code,
                    subject_type,
                    weekly_hours,
                    department_id
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                subject_name,
                subject_code,
                subject_type,
                weekly_hours,
                department_id or None
            ))
            flash("Subject added successfully.", "success")

        connection.commit()

    except Error as error:
        connection.rollback()
        print("Subject save error:", error)
        flash(f"Unable to save subject: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("subjects"))


# ADMIN ONLY: DELETE SUBJECT
@app.route("/subjects/delete/<int:subject_id>")
@admin_required
def delete_subject(subject_id):
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("subjects"))

    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM timetable WHERE subject_id=%s",
            (subject_id,)
        )

        cursor.execute(
            "DELETE FROM subject_faculty WHERE subject_id=%s",
            (subject_id,)
        )

        cursor.execute(
            "DELETE FROM class_subjects WHERE subject_id=%s",
            (subject_id,)
        )

        cursor.execute(
            "DELETE FROM subjects WHERE subject_id=%s",
            (subject_id,)
        )

        connection.commit()
        flash("Subject deleted successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Subject delete error:", error)
        flash(f"Unable to delete subject: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("subjects"))

# ============================================================
# CLASSES
# ============================================================

@app.route("/classes")
@login_required
def classes():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template("classes.html", classes=[], departments=[])

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT c.class_id, c.class_name, c.year, c.section,
                   c.semester, c.department_id, d.department_name
            FROM classes c
            LEFT JOIN departments d ON c.department_id = d.department_id
            ORDER BY c.class_id DESC
        """)
        classes_data = cursor.fetchall()

        cursor.execute("""
            SELECT department_id, department_name
            FROM departments
            ORDER BY department_name
        """)
        departments_data = cursor.fetchall()

    except Error as error:
        print("Classes loading error:", error)
        classes_data = []
        departments_data = []
        flash(f"Unable to load classes: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return render_template(
        "classes.html",
        classes=classes_data,
        departments=departments_data
    )


# ============================================================
# SAVE CLASS
# ============================================================

@app.route("/classes/save", methods=["POST"])
@admin_required
def save_class():
    class_id = request.form.get("class_id", "").strip()
    class_name = request.form.get("class_name", "").strip()
    year = request.form.get("year", "").strip()
    section = request.form.get("section", "").strip()
    semester = request.form.get("semester", "").strip()
    department_id = request.form.get("department_id", "").strip()

    if not all([class_name, year, section, semester, department_id]):
        flash("Please fill in all class fields.", "error")
        return redirect(url_for("classes"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("classes"))

    cursor = connection.cursor()

    try:
        if class_id:
            cursor.execute("""
                UPDATE classes
                SET class_name = %s, year = %s, section = %s,
                    semester = %s, department_id = %s
                WHERE class_id = %s
            """, (
                class_name, year, section, semester,
                department_id, class_id
            ))
            flash("Class updated successfully.", "success")

        else:
            cursor.execute("""
                INSERT INTO classes
                    (class_name, year, section, semester, department_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                class_name, year, section, semester, department_id
            ))
            flash("Class added successfully.", "success")

        connection.commit()

    except Error as error:
        connection.rollback()
        print("Class save error:", error)
        flash(f"Unable to save class: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("classes"))


# ============================================================
# DELETE CLASS
# ============================================================

@app.route(
    "/classes/delete/<int:class_id>",
    methods=["GET", "POST"]
)
@admin_required
def delete_class(class_id):
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("classes"))

    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM timetable WHERE class_id = %s",
            (class_id,)
        )
        cursor.execute(
            "DELETE FROM class_subjects WHERE class_id = %s",
            (class_id,)
        )
        cursor.execute(
            "DELETE FROM classes WHERE class_id = %s",
            (class_id,)
        )

        deleted_rows = cursor.rowcount
        connection.commit()

        if deleted_rows > 0:
            flash("Class deleted successfully.", "success")
        else:
            flash("Class was not found.", "error")

    except Error as error:
        connection.rollback()
        print("Class delete error:", error)
        flash(f"Unable to delete class: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("classes"))
# ============================================================
# ROOMS
# ============================================================

@app.route("/rooms")
@login_required
def rooms():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template("rooms.html", rooms=[])

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT room_id, room_number, room_type, capacity, building
            FROM rooms
            ORDER BY room_id DESC
        """)
        rooms_data = cursor.fetchall()

    except Error as error:
        print("Rooms loading error:", error)
        rooms_data = []
        flash(f"Unable to load rooms: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return render_template("rooms.html", rooms=rooms_data)


# ============================================================
# SAVE ROOM
# ============================================================

@app.route("/rooms/save", methods=["POST"])
@admin_required
def save_room():
    room_id = request.form.get("room_id", "").strip()
    room_number = request.form.get("room_number", "").strip()
    room_type = request.form.get("room_type", "Classroom").strip()
    capacity = request.form.get("capacity", "0").strip()
    building = request.form.get("building", "").strip()

    if not room_number:
        flash("Room number is required.", "error")
        return redirect(url_for("rooms"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("rooms"))

    cursor = connection.cursor()

    try:
        if room_id:
            cursor.execute("""
                UPDATE rooms
                SET room_number = %s, room_type = %s,
                    capacity = %s, building = %s
                WHERE room_id = %s
            """, (room_number, room_type, capacity, building, room_id))

            flash("Room updated successfully.", "success")

        else:
            cursor.execute("""
                INSERT INTO rooms
                    (room_number, room_type, capacity, building)
                VALUES (%s, %s, %s, %s)
            """, (room_number, room_type, capacity, building))

            flash("Room added successfully.", "success")

        connection.commit()

    except Error as error:
        connection.rollback()
        print("Room save error:", error)
        flash(f"Unable to save room: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("rooms"))


# ============================================================
# DELETE ROOM
# ============================================================

@app.route("/rooms/delete/<int:room_id>")
@admin_required
def delete_room(room_id):
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("rooms"))

    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM timetable WHERE room_id = %s",
            (room_id,)
        )
        cursor.execute(
            "DELETE FROM rooms WHERE room_id = %s",
            (room_id,)
        )

        connection.commit()
        flash("Room deleted successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Room delete error:", error)
        flash(f"Unable to delete room: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("rooms"))
#
# ============================================================
# TIME SLOTS
# ============================================================

@app.route("/time-slots", methods=["GET"])
@login_required
def time_slots():
    connection = None
    cursor = None
    slots_data = []

    try:
        connection = get_connection()

        if connection is None:
            flash("Database connection failed. Please check MySQL.", "error")
            return render_template(
                "time_slots.html",
                slots=[],
                time_slots=[]
            )

        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                slot_id,
                day_of_week,
                period_number,
                start_time,
                end_time
            FROM time_slots
            ORDER BY
                FIELD(
                    UPPER(day_of_week),
                    'MONDAY',
                    'TUESDAY',
                    'WEDNESDAY',
                    'THURSDAY',
                    'FRIDAY',
                    'SATURDAY',
                    'SUNDAY'
                ),
                period_number
        """)

        slots_data = cursor.fetchall()

        # Convert MySQL time values to strings for HTML.
        for slot in slots_data:
            if slot.get("start_time") is not None:
                slot["start_time"] = str(slot["start_time"])

            if slot.get("end_time") is not None:
                slot["end_time"] = str(slot["end_time"])

        print(f"Time slots loaded successfully: {len(slots_data)}")

    except Error as error:
        print("Time slots loading error:", error)
        flash(f"Unable to load time slots: {error}", "error")

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    # Support both variable names used by HTML templates.
    return render_template(
        "time_slots.html",
        slots=slots_data,
        time_slots=slots_data
    )

# ============================================================
# SAVE TIME SLOT
# ============================================================

@app.route("/time-slots/save", methods=["POST"])
@admin_required
def save_time_slot():
    slot_id = request.form.get("slot_id", "").strip()
    day_of_week = request.form.get("day_of_week", "").strip().upper()
    period_number = request.form.get("period_number", "").strip()
    start_time = request.form.get("start_time", "").strip()
    end_time = request.form.get("end_time", "").strip()

    valid_days = [
        "MONDAY", "TUESDAY", "WEDNESDAY",
        "THURSDAY", "FRIDAY", "SATURDAY"
    ]

    if day_of_week not in valid_days:
        flash("Please select a valid working day.", "error")
        return redirect(url_for("time_slots"))

    if not start_time or not end_time:
        flash("Start time and end time are required.", "error")
        return redirect(url_for("time_slots"))

    if start_time >= end_time:
        flash("End time must be later than start time.", "error")
        return redirect(url_for("time_slots"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("time_slots"))

    cursor = connection.cursor()

    try:
        if not period_number:
            cursor.execute("""
                SELECT COALESCE(MAX(period_number), 0)
                FROM time_slots
                WHERE day_of_week = %s
            """, (day_of_week,))
            period_number = int(cursor.fetchone()[0]) + 1
        else:
            try:
                period_number = int(period_number)
            except ValueError:
                flash("Period number must be a valid number.", "error")
                return redirect(url_for("time_slots"))

        if period_number < 1:
            flash("Period number must be greater than 0.", "error")
            return redirect(url_for("time_slots"))

        # Check whether this day already has that period number.
        if slot_id:
            cursor.execute("""
                SELECT slot_id FROM time_slots
                WHERE day_of_week = %s
                  AND period_number = %s
                  AND slot_id != %s
            """, (day_of_week, period_number, slot_id))
        else:
            cursor.execute("""
                SELECT slot_id FROM time_slots
                WHERE day_of_week = %s
                  AND period_number = %s
            """, (day_of_week, period_number))

        if cursor.fetchone():
            flash("That period number already exists for this day.", "error")
            return redirect(url_for("time_slots"))

        if slot_id:
            cursor.execute("""
                UPDATE time_slots
                SET day_of_week = %s, period_number = %s,
                    start_time = %s, end_time = %s
                WHERE slot_id = %s
            """, (
                day_of_week, period_number,
                start_time, end_time, slot_id
            ))
            flash("Time slot updated successfully.", "success")

        else:
            cursor.execute("""
                INSERT INTO time_slots
                    (day_of_week, period_number, start_time, end_time)
                VALUES (%s, %s, %s, %s)
            """, (
                day_of_week, period_number, start_time, end_time
            ))
            flash("Time slot added successfully.", "success")

        connection.commit()

    except Error as error:
        connection.rollback()
        print("Time slot save error:", error)
        flash(f"Unable to save time slot: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("time_slots"))


# ============================================================
# DELETE TIME SLOT
# ============================================================

@app.route("/time-slots/delete/<int:slot_id>")
@admin_required
def delete_time_slot(slot_id):
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("time_slots"))

    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM timetable WHERE slot_id = %s",
            (slot_id,)
        )
        cursor.execute(
            "DELETE FROM time_slots WHERE slot_id = %s",
            (slot_id,)
        )

        connection.commit()
        flash("Time slot deleted successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Time slot delete error:", error)
        flash(f"Unable to delete time slot: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("time_slots"))
# ============================================================
# FACULTY AVAILABILITY
# ============================================================

# ============================================================
# FACULTY AVAILABILITY
# ============================================================

@app.route("/faculty-availability")
@login_required
def faculty_availability():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template(
            "faculty_availability.html",
            faculty_list=[],
            availability_list=[]
        )

    cursor = connection.cursor(dictionary=True)

    try:
        # Get faculty members for the dropdown
        cursor.execute("""
            SELECT faculty_id, faculty_name, employee_id
            FROM faculty
            ORDER BY faculty_name
        """)
        faculty_data = cursor.fetchall()

        # Get availability records with faculty and time-slot details
        cursor.execute("""
            SELECT
                fa.faculty_id,
                fa.slot_id,
                fa.is_available,
                f.faculty_name,
                f.employee_id,
                ts.day_of_week,
                ts.period_number,
                ts.start_time,
                ts.end_time
            FROM faculty_availability fa
            JOIN faculty f
                ON fa.faculty_id = f.faculty_id
            JOIN time_slots ts
                ON fa.slot_id = ts.slot_id
            ORDER BY
                f.faculty_name,
                FIELD(
                    ts.day_of_week,
                    'MONDAY', 'TUESDAY', 'WEDNESDAY',
                    'THURSDAY', 'FRIDAY', 'SATURDAY'
                ),
                ts.period_number
        """)
        availability_data = cursor.fetchall()

        # Convert times to strings for display
        for item in availability_data:
            if item.get("start_time") is not None:
                item["start_time"] = str(item["start_time"])

            if item.get("end_time") is not None:
                item["end_time"] = str(item["end_time"])

    except Error as error:
        print("Faculty availability error:", error)
        flash(f"Unable to load faculty availability: {error}", "error")
        faculty_data = []
        availability_data = []

    finally:
        close_connection(connection, cursor)

    # Match the variable names expected by faculty_availability.html
    return render_template(
        "faculty_availability.html",
        faculty_list=faculty_data,
        availability_list=availability_data
    )



# ============================================================
# TOGGLE FACULTY AVAILABILITY
# ============================================================

@app.route("/faculty-availability/toggle", methods=["POST"])
@admin_required
def toggle_faculty_availability():
    faculty_id = request.form.get("faculty_id", "").strip()
    time_slot_id = request.form.get("time_slot_id", "").strip()
    is_available = request.form.get("is_available", "1").strip()

    # Validate required fields
    if not faculty_id or not time_slot_id:
        flash("Faculty and time slot are required.", "error")
        return redirect(url_for("faculty_availability"))

    # Validate availability value
    if is_available not in ("0", "1"):
        flash("Invalid availability value.", "error")
        return redirect(url_for("faculty_availability"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("faculty_availability"))

    cursor = connection.cursor()

    try:
        # Insert or update faculty availability
        cursor.execute("""
            INSERT INTO faculty_availability
                (faculty_id, slot_id, is_available)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                is_available = VALUES(is_available)
        """, (int(faculty_id), int(time_slot_id), int(is_available)))

        connection.commit()

        flash("Faculty availability updated successfully.", "success")

    except (Error, ValueError) as error:
        connection.rollback()
        print("Availability update error:", error)
        flash(f"Unable to update availability: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("faculty_availability"))

# ============================================================
# SUBJECT - FACULTY
# ============================================================

@app.route("/subject-faculty")
@login_required
def subject_faculty():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template(
            "subject_faculty.html",
            assignments=[],
            subjects=[],
            faculty=[]
        )

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT sf.subject_faculty_id, sf.subject_id, sf.faculty_id,
                   s.subject_name, s.subject_code, f.faculty_name
            FROM subject_faculty sf
            INNER JOIN subjects s ON sf.subject_id = s.subject_id
            INNER JOIN faculty f ON sf.faculty_id = f.faculty_id
            ORDER BY sf.subject_faculty_id DESC
        """)
        assignments = cursor.fetchall()

        cursor.execute("""
            SELECT subject_id, subject_name, subject_code
            FROM subjects
            ORDER BY subject_name
        """)
        subjects_data = cursor.fetchall()

        cursor.execute("""
            SELECT faculty_id, faculty_name
            FROM faculty
            ORDER BY faculty_name
        """)
        faculty_data = cursor.fetchall()

    except Error as error:
        print("Subject-faculty loading error:", error)
        assignments = []
        subjects_data = []
        faculty_data = []
        flash(f"Unable to load subject-faculty mapping: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return render_template(
        "subject_faculty.html",
        assignments=assignments,
        subjects=subjects_data,
        faculty=faculty_data
    )


# ============================================================
# SAVE SUBJECT - FACULTY ASSIGNMENT
# ============================================================

@app.route("/subject-faculty/save", methods=["POST"])
@admin_required
def save_subject_faculty():
    subject_id = request.form.get("subject_id")
    faculty_id = request.form.get("faculty_id")

    if not subject_id or not faculty_id:
        flash("Subject and faculty are required.", "error")
        return redirect(url_for("subject_faculty"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("subject_faculty"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT subject_faculty_id
            FROM subject_faculty
            WHERE subject_id = %s AND faculty_id = %s
        """, (subject_id, faculty_id))

        if cursor.fetchone():
            flash("This subject is already assigned to that faculty member.", "error")
        else:
            cursor.execute("""
                INSERT INTO subject_faculty (subject_id, faculty_id)
                VALUES (%s, %s)
            """, (subject_id, faculty_id))

            connection.commit()
            flash("Subject assigned to faculty successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Subject-faculty save error:", error)
        flash(f"Unable to save assignment: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("subject_faculty"))


# ============================================================
# DELETE SUBJECT - FACULTY ASSIGNMENT
# ============================================================
@app.route(
    "/subject-faculty/delete/<int:assignment_id>",
    methods=["POST"]
)
@admin_required
def delete_subject_faculty(assignment_id):
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("subject_faculty"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM subject_faculty
            WHERE subject_faculty_id = %s
        """, (assignment_id,))

        if cursor.rowcount > 0:
            connection.commit()
            flash("Subject-faculty assignment deleted successfully.", "success")
        else:
            flash("Assignment not found.", "error")

    except Error as error:
        connection.rollback()
        print("Subject-faculty delete error:", error)
        flash(f"Unable to delete assignment: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("subject_faculty"))
# ============================================================
# CLASS - SUBJECT
# ============================================================

@app.route("/class-subjects")
@login_required
def class_subjects():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template(
            "class_subjects.html",
            assignments=[],
            classes_list=[],
            subjects_list=[]
        )

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT cs.class_subject_id, cs.class_id, cs.subject_id,
                   cs.weekly_hours, c.class_name, c.year, c.semester,
                   s.subject_name, s.subject_code
            FROM class_subjects cs
            INNER JOIN classes c ON cs.class_id = c.class_id
            INNER JOIN subjects s ON cs.subject_id = s.subject_id
            ORDER BY cs.class_subject_id DESC
        """)
        assignments = cursor.fetchall()

        cursor.execute("""
            SELECT class_id, class_name, year, semester
            FROM classes
            ORDER BY class_name
        """)
        classes_data = cursor.fetchall()

        cursor.execute("""
            SELECT subject_id, subject_name, subject_code, weekly_hours
            FROM subjects
            ORDER BY subject_name
        """)
        subjects_data = cursor.fetchall()

    except Error as error:
        print("Class-subject loading error:", error)
        assignments = []
        classes_data = []
        subjects_data = []
        flash(f"Unable to load class-subject mappings: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return render_template(
        "class_subjects.html",
        assignments=assignments,
        classes_list=classes_data,
        subjects_list=subjects_data
    )


# ============================================================
# SAVE CLASS - SUBJECT ASSIGNMENT
# ============================================================

@app.route("/class-subjects/save", methods=["POST"])
@admin_required
def save_class_subject():
    class_id = request.form.get("class_id")
    subject_id = request.form.get("subject_id")
    weekly_hours = request.form.get("weekly_hours", "1")

    if not class_id or not subject_id:
        flash("Class and subject are required.", "error")
        return redirect(url_for("class_subjects"))

    try:
        weekly_hours = int(weekly_hours)
        if weekly_hours < 1:
            raise ValueError
    except (ValueError, TypeError):
        flash("Weekly hours must be a positive number.", "error")
        return redirect(url_for("class_subjects"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("class_subjects"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO class_subjects
                (class_id, subject_id, weekly_hours)
            VALUES (%s, %s, %s)
        """, (class_id, subject_id, weekly_hours))

        connection.commit()
        flash("Class-subject assignment added successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Class-subject save error:", error)
        flash(f"Unable to save class-subject assignment: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("class_subjects"))


# ============================================================
# DELETE CLASS - SUBJECT ASSIGNMENT
# ============================================================

@app.route("/class-subjects/delete/<int:assignment_id>")
@admin_required
def delete_class_subject(assignment_id):
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("class_subjects"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM class_subjects
            WHERE class_subject_id = %s
        """, (assignment_id,))

        connection.commit()
        flash("Class-subject assignment deleted successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Class-subject delete error:", error)
        flash(f"Unable to delete assignment: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("class_subjects"))

# ============================================================
# FACULTY LEAVE MANAGEMENT
# ============================================================

@app.route("/faculty-leave", methods=["GET", "POST"])
@login_required
def faculty_leave():

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("dashboard"))

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        # Identify the faculty member using the logged-in account email.
        cursor.execute("""
            SELECT
                u.user_id,
                u.email,
                f.faculty_id,
                f.faculty_name
            FROM users u
            INNER JOIN faculty f
                ON LOWER(TRIM(u.email)) = LOWER(TRIM(f.email))
            WHERE u.user_id = %s
              AND u.role = 'STAFF'
        """, (session["user_id"],))

        faculty_member = cursor.fetchone()

        if not faculty_member:
            flash(
                "Your account is not linked to a faculty record. "
                "Please contact the administrator.",
                "error"
            )
            return redirect(url_for("dashboard"))

        if request.method == "POST":

            start_date = request.form.get("start_date", "").strip()
            end_date = request.form.get("end_date", "").strip()
            leave_type = request.form.get("leave_type", "").strip()
            reason = request.form.get("reason", "").strip()

            try:
                start = date.fromisoformat(start_date)
                end = date.fromisoformat(end_date)
            except ValueError:
                flash("Please enter valid leave dates.", "error")
                return redirect(url_for("faculty_leave"))

            if start < date.today():
                flash("Leave cannot start in the past.", "error")
                return redirect(url_for("faculty_leave"))

            if end < start:
                flash("End date cannot be before start date.", "error")
                return redirect(url_for("faculty_leave"))

            if leave_type not in (
                "Casual Leave",
                "Medical Leave",
                "Emergency Leave",
                "Other"
            ):
                flash("Please select a valid leave type.", "error")
                return redirect(url_for("faculty_leave"))

            if len(reason) < 5:
                flash("Please provide a reason of at least 5 characters.", "error")
                return redirect(url_for("faculty_leave"))

            # Prevent overlapping pending or approved leave requests.
            cursor.execute("""
                SELECT leave_id
                FROM faculty_leave_requests
                WHERE faculty_id = %s
                  AND status IN ('PENDING', 'APPROVED')
                  AND start_date <= %s
                  AND end_date >= %s
                LIMIT 1
            """, (
                faculty_member["faculty_id"],
                end,
                start
            ))

            if cursor.fetchone():
                flash(
                    "You already have a pending or approved leave "
                    "request overlapping these dates.",
                    "error"
                )
                return redirect(url_for("faculty_leave"))

            cursor.execute("""
                INSERT INTO faculty_leave_requests (
                    faculty_id,
                    user_id,
                    start_date,
                    end_date,
                    leave_type,
                    reason
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                faculty_member["faculty_id"],
                faculty_member["user_id"],
                start,
                end,
                leave_type,
                reason
            ))

            connection.commit()

            flash(
                "Your leave request has been submitted successfully.",
                "success"
            )

            return redirect(url_for("faculty_leave"))

        # Display this faculty member's previous requests.
        cursor.execute("""
            SELECT
                leave_id,
                start_date,
                end_date,
                leave_type,
                reason,
                status,
                admin_remarks,
                created_at
            FROM faculty_leave_requests
            WHERE faculty_id = %s
            ORDER BY created_at DESC
        """, (faculty_member["faculty_id"],))

        leave_requests = cursor.fetchall()

        return render_template(
    "faculty_leave.html",
    faculty=faculty_member,
    leave_requests=leave_requests,
    today=date.today().isoformat()
)

    except Error as error:
        if connection:
            connection.rollback()

        print("Faculty leave error:", error)
        flash("Unable to process your leave request.", "error")
        return redirect(url_for("dashboard"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

# ============================================================
# ADMIN - VIEW FACULTY LEAVE REQUESTS
# ============================================================

@app.route("/admin/leave-requests")
@admin_required
def admin_leave_requests():

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("dashboard"))

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                lr.leave_id,
                lr.faculty_id,
                lr.user_id,
                lr.start_date,
                lr.end_date,
                lr.leave_type,
                lr.reason,
                lr.status,
                lr.admin_remarks,
                lr.created_at,
                f.faculty_name,
                f.employee_id,
                f.email
            FROM faculty_leave_requests lr
            INNER JOIN faculty f
                ON lr.faculty_id = f.faculty_id
            ORDER BY
                CASE
                    WHEN lr.status = 'PENDING' THEN 0
                    ELSE 1
                END,
                lr.created_at DESC
        """)

        leave_requests = cursor.fetchall()

        return render_template(
            "admin_leave_requests.html",
            leave_requests=leave_requests
        )

    except Error as error:
        print("Admin leave requests error:", error)
        flash("Unable to load faculty leave requests.", "error")
        return redirect(url_for("dashboard"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

# ============================================================
# ADMIN - APPROVE OR REJECT FACULTY LEAVE
# ============================================================

@app.route("/admin/leave-requests/<int:leave_id>/update", methods=["POST"])
@admin_required
def update_leave_request(leave_id):

    action = request.form.get("action", "").upper()
    admin_remarks = request.form.get("admin_remarks", "").strip()

    if action not in ["APPROVED", "REJECTED"]:
        flash("Invalid leave action.", "error")
        return redirect(url_for("admin_leave_requests"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("admin_leave_requests"))

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE faculty_leave_requests
            SET status = %s,
                admin_remarks = %s
            WHERE leave_id = %s
              AND status = 'PENDING'
        """, (action, admin_remarks, leave_id))

        if cursor.rowcount == 0:
            connection.rollback()
            flash(
                "Request not found or it has already been processed.",
                "error"
            )
        else:
            connection.commit()
            flash(
                f"Leave request {action.lower()} successfully!",
                "success"
            )

    except Error as error:
        connection.rollback()
        print("Leave update error:", error)
        flash("Unable to update leave request.", "error")

    finally:
        if cursor is not None:
            cursor.close()

        connection.close()

    return redirect(url_for("admin_leave_requests"))

# ============================================================
# ADMIN - MANAGE SUBSTITUTE FACULTY
# ============================================================

@app.route("/admin/leave-requests/<int:leave_id>/substitutes")
@admin_required
def manage_substitutes(leave_id):

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("admin_leave_requests"))

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        # Get the approved leave request.
        cursor.execute("""
            SELECT
                lr.leave_id,
                lr.faculty_id,
                lr.start_date,
                lr.end_date,
                lr.status,
                f.faculty_name,
                f.employee_id
            FROM faculty_leave_requests lr
            INNER JOIN faculty f
                ON lr.faculty_id = f.faculty_id
            WHERE lr.leave_id = %s
              AND lr.status = 'APPROVED'
        """, (leave_id,))

        leave = cursor.fetchone()

        if not leave:
            flash(
                "Approved leave request not found.",
                "error"
            )
            return redirect(url_for("admin_leave_requests"))

        sessions = []

        current_date = leave["start_date"]
        end_date = leave["end_date"]

        # Check every calendar date in the approved leave period.
        while current_date <= end_date:

            day_name = current_date.strftime("%A").upper()

            cursor.execute("""
                SELECT
                    t.timetable_id,
                    t.class_id,
                    t.subject_id,
                    t.faculty_id,
                    t.room_id,
                    t.slot_id,
                    c.class_name,
                    s.subject_name,
                    s.subject_code,
                    ts.day_of_week,
                    ts.period_number,
                    ts.start_time,
                    ts.end_time,
                    r.room_number
                FROM timetable t
                INNER JOIN time_slots ts
                    ON t.slot_id = ts.slot_id
                INNER JOIN classes c
                    ON t.class_id = c.class_id
                INNER JOIN subjects s
                    ON t.subject_id = s.subject_id
                LEFT JOIN rooms r
                    ON t.room_id = r.room_id
                WHERE t.faculty_id = %s
                  AND ts.day_of_week = %s
                ORDER BY ts.period_number
            """, (
                leave["faculty_id"],
                day_name
            ))

            daily_sessions = cursor.fetchall()

            for timetable_session in daily_sessions:

                # Find qualified faculty who are available
                # and have no timetable or confirmed-substitute clash.
                cursor.execute("""
                    SELECT
                        f.faculty_id,
                        f.faculty_name,
                        f.employee_id
                    FROM subject_faculty sf
                    INNER JOIN faculty f
                        ON sf.faculty_id = f.faculty_id
                    LEFT JOIN faculty_availability fa
                        ON fa.faculty_id = f.faculty_id
                       AND fa.slot_id = %s
                    WHERE sf.subject_id = %s
                      AND f.faculty_id != %s
                      AND COALESCE(fa.is_available, 1) = 1

                      AND NOT EXISTS (
                          SELECT 1
                          FROM timetable existing
                          WHERE existing.faculty_id = f.faculty_id
                            AND existing.slot_id = %s
                      )

                      AND NOT EXISTS (
                          SELECT 1
                          FROM faculty_substitutions fs
                          INNER JOIN timetable existing
                              ON fs.timetable_id = existing.timetable_id
                          WHERE fs.substitute_faculty_id = f.faculty_id
                            AND fs.class_date = %s
                            AND fs.status = 'CONFIRMED'
                            AND existing.slot_id = %s
                      )

                    ORDER BY f.faculty_name
                """, (
                    timetable_session["slot_id"],
                    timetable_session["subject_id"],
                    leave["faculty_id"],
                    timetable_session["slot_id"],
                    current_date,
                    timetable_session["slot_id"]
                ))

                timetable_session["eligible_faculty"] = cursor.fetchall()

                # Check whether a substitution already exists.
                cursor.execute("""
                    SELECT
                        fs.substitution_id,
                        fs.substitute_faculty_id,
                        fs.status,
                        f.faculty_name AS substitute_name
                    FROM faculty_substitutions fs
                    LEFT JOIN faculty f
                        ON fs.substitute_faculty_id = f.faculty_id
                    WHERE fs.timetable_id = %s
                      AND fs.class_date = %s
                """, (
                    timetable_session["timetable_id"],
                    current_date
                ))

                timetable_session["substitution"] = cursor.fetchone()
                timetable_session["class_date"] = current_date

                sessions.append(timetable_session)

            from datetime import timedelta
            current_date += timedelta(days=1)

        return render_template(
            "admin_substitutions.html",
            leave=leave,
            sessions=sessions
        )

    except Error as error:
        print("Substitute management error:", error)
        flash(
            "Unable to load substitute faculty details.",
            "error"
        )
        return redirect(url_for("admin_leave_requests"))

    finally:
        if cursor is not None:
            cursor.close()

        connection.close()



# ============================================================
# ADMIN - ASSIGN SUBSTITUTE FACULTY
# ============================================================

@app.route(
    "/admin/assign-substitute/<int:leave_id>",
    methods=["POST"]
)
@admin_required
def assign_substitute(leave_id):

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(
            url_for("manage_substitutes", leave_id=leave_id)
        )

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        timetable_id = request.form.get("timetable_id", type=int)
        substitute_id = request.form.get(
            "substitute_faculty_id", type=int
        )
        class_date = request.form.get("class_date")

        if not timetable_id or not substitute_id or not class_date:
            flash("Please select a valid substitute faculty.", "error")
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        from datetime import datetime

        try:
            class_date = datetime.strptime(
                class_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            flash("Invalid class date.", "error")
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        # 1. Verify approved leave.
        cursor.execute("""
            SELECT faculty_id, start_date, end_date
            FROM faculty_leave_requests
            WHERE leave_id = %s
              AND status = 'APPROVED'
            FOR UPDATE
        """, (leave_id,))

        leave = cursor.fetchone()

        if not leave:
            flash("Approved leave request not found.", "error")
            return redirect(url_for("admin_leave_requests"))

        if not (leave["start_date"] <= class_date <= leave["end_date"]):
            flash("Selected date is outside the approved leave period.", "error")
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        # 2. Verify the affected timetable session.
        cursor.execute("""
            SELECT
                t.timetable_id,
                t.faculty_id,
                t.subject_id,
                t.slot_id,
                ts.day_of_week
            FROM timetable t
            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id
            WHERE t.timetable_id = %s
              AND t.faculty_id = %s
            FOR UPDATE
        """, (timetable_id, leave["faculty_id"]))

        timetable_session = cursor.fetchone()

        if not timetable_session:
            flash("Invalid timetable session.", "error")
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        if timetable_session["day_of_week"].upper() != class_date.strftime("%A").upper():
            flash("The selected date does not match the timetable day.", "error")
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        # 3. Check subject qualification.
        cursor.execute("""
            SELECT 1
            FROM subject_faculty
            WHERE subject_id = %s
              AND faculty_id = %s
        """, (
            timetable_session["subject_id"],
            substitute_id
        ))

        if not cursor.fetchone():
            flash(
                "This faculty member is not qualified for the subject.",
                "error"
            )
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        # 4. Check faculty availability.
        cursor.execute("""
            SELECT is_available
            FROM faculty_availability
            WHERE faculty_id = %s
              AND slot_id = %s
        """, (
            substitute_id,
            timetable_session["slot_id"]
        ))

        availability = cursor.fetchone()

        if availability and not availability["is_available"]:
            flash("Selected faculty is unavailable for this period.", "error")
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        # 5. Check regular timetable clash.
        cursor.execute("""
            SELECT 1
            FROM timetable
            WHERE faculty_id = %s
              AND slot_id = %s
            LIMIT 1
        """, (
            substitute_id,
            timetable_session["slot_id"]
        ))

        if cursor.fetchone():
            flash(
                "Selected faculty already has a class in this period.",
                "error"
            )
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        # 6. Check confirmed substitution clash on this date.
        cursor.execute("""
            SELECT 1
            FROM faculty_substitutions fs
            INNER JOIN timetable t
                ON fs.timetable_id = t.timetable_id
            WHERE fs.substitute_faculty_id = %s
              AND fs.class_date = %s
              AND fs.status = 'CONFIRMED'
              AND t.slot_id = %s
            LIMIT 1
        """, (
            substitute_id,
            class_date,
            timetable_session["slot_id"]
        ))

        if cursor.fetchone():
            flash(
                "Selected faculty already has a confirmed substitute class at this time.",
                "error"
            )
            return redirect(
                url_for("manage_substitutes", leave_id=leave_id)
            )

        # 7. Save or update the substitution.
        cursor.execute("""
            INSERT INTO faculty_substitutions (
                leave_id,
                timetable_id,
                class_date,
                original_faculty_id,
                substitute_faculty_id,
                status
            )
            VALUES (%s, %s, %s, %s, %s, 'CONFIRMED')

            ON DUPLICATE KEY UPDATE
                leave_id = VALUES(leave_id),
                original_faculty_id = VALUES(original_faculty_id),
                substitute_faculty_id = VALUES(substitute_faculty_id),
                status = 'CONFIRMED'
        """, (
            leave_id,
            timetable_id,
            class_date,
            leave["faculty_id"],
            substitute_id
        ))

        connection.commit()

        flash("Substitute faculty assigned successfully!", "success")

    except Error as error:
        connection.rollback()
        print("Substitute assignment error:", error)
        flash("Unable to assign substitute faculty.", "error")

    finally:
        if cursor is not None:
            cursor.close()

        connection.close()

    return redirect(
        url_for("manage_substitutes", leave_id=leave_id)
    )

        
# ============================================================
# GENERATE TIMETABLE
# ============================================================

@app.route("/generate-timetable", methods=["GET", "POST"])
@admin_required
def generate():

    # If the page is opened directly, return to the timetable.
    if request.method == "GET":
        flash(
            "Please use the Generate Timetable button to generate the timetable.",
            "info"
        )
        return redirect(url_for("timetable"))

    try:
        success, message, count = generate_timetable()

        if success:
            flash(message, "success")
        else:
            flash(message, "error")

    except Exception as error:
        print("Timetable generation error:", error)
        flash(
            f"Timetable generation failed: {error}",
            "error"
        )

    return redirect(url_for("timetable"))

# ============================================================
# VIEW TIMETABLE
# ============================================================

@app.route("/timetable")
@login_required
def timetable():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template(
            "timetable.html",
            timetable=[],
            classes=[],
            faculty=[],
            rooms=[],
            slots=[],
            entries=[]
        )

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                t.timetable_id,
                t.class_id,
                t.subject_id,
                t.faculty_id,
                t.room_id,
                t.slot_id,
                c.class_name,
                s.subject_name,
                s.subject_code,
                f.faculty_name,
                r.room_number,
                r.room_type,
                ts.day_of_week,
                ts.period_number,
                ts.start_time,
                ts.end_time
            FROM timetable t
            LEFT JOIN time_slots ts
                ON t.slot_id = ts.slot_id
            LEFT JOIN classes c
                ON t.class_id = c.class_id
            LEFT JOIN subjects s
                ON t.subject_id = s.subject_id
            LEFT JOIN faculty f
                ON t.faculty_id = f.faculty_id
            LEFT JOIN rooms r
                ON t.room_id = r.room_id
            ORDER BY
                FIELD(
                    ts.day_of_week,
                    'MONDAY', 'TUESDAY', 'WEDNESDAY',
                    'THURSDAY', 'FRIDAY', 'SATURDAY'
                ),
                ts.period_number,
                c.class_name
        """)
        timetable_data = cursor.fetchall()

        cursor.execute("SELECT * FROM classes ORDER BY class_name")
        classes_data = cursor.fetchall()

        cursor.execute("SELECT * FROM faculty ORDER BY faculty_name")
        faculty_data = cursor.fetchall()

        cursor.execute("SELECT * FROM rooms ORDER BY room_number")
        rooms_data = cursor.fetchall()

        cursor.execute("""
            SELECT *
            FROM time_slots
            ORDER BY
                FIELD(
                    day_of_week,
                    'MONDAY', 'TUESDAY', 'WEDNESDAY',
                    'THURSDAY', 'FRIDAY', 'SATURDAY'
                ),
                period_number
        """)
        slots_data = cursor.fetchall()

    except Error as error:
        print("Timetable loading error:", error)
        flash(f"Unable to load timetable: {error}", "error")
        timetable_data = []
        classes_data = []
        faculty_data = []
        rooms_data = []
        slots_data = []

    finally:
        close_connection(connection, cursor)

    return render_template(
        "timetable.html",
        timetable=timetable_data,
        classes=classes_data,
        faculty=faculty_data,
        rooms=rooms_data,
        slots=slots_data,
        slot_list=slots_data,
        entries=timetable_data
    )



# ============================================================
# EDIT TIMETABLE
# ============================================================

@app.route("/timetable/download-pdf")
@login_required
def download_timetable_pdf():
    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("timetable"))

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                c.class_name,
                s.subject_code,
                s.subject_name,
                f.faculty_name,
                r.room_number,
                ts.day_of_week,
                ts.period_number,
                ts.start_time,
                ts.end_time
            FROM timetable t
            LEFT JOIN classes c ON t.class_id = c.class_id
            LEFT JOIN subjects s ON t.subject_id = s.subject_id
            LEFT JOIN faculty f ON t.faculty_id = f.faculty_id
            LEFT JOIN rooms r ON t.room_id = r.room_id
            LEFT JOIN time_slots ts ON t.slot_id = ts.slot_id
            ORDER BY
                FIELD(
                    ts.day_of_week,
                    'MONDAY', 'TUESDAY', 'WEDNESDAY',
                    'THURSDAY', 'FRIDAY', 'SATURDAY'
                ),
                ts.period_number,
                c.class_name
        """)
        rows = cursor.fetchall()

    except Error as error:
        print("PDF export error:", error)
        flash("Unable to create timetable PDF.", "error")
        return redirect(url_for("timetable"))

    finally:
        close_connection(connection, cursor)

    if not rows:
        flash("No timetable entries available to export.", "error")
        return redirect(url_for("timetable"))

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(A4),
        rightMargin=20,
        leftMargin=20,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph("Faculty Timetable", styles["Title"]),
        Spacer(1, 15)
    ]

    table_data = [[
        "Day", "Period", "Start", "End",
        "Class", "Subject Code", "Subject",
        "Faculty", "Room"
    ]]

    for row in rows:
        table_data.append([
            str(row.get("day_of_week") or "-").title(),
            str(row.get("period_number") or "-"),
            str(row.get("start_time") or "-"),
            str(row.get("end_time") or "-"),
            str(row.get("class_name") or "-"),
            str(row.get("subject_code") or "-"),
            str(row.get("subject_name") or "-"),
            str(row.get("faculty_name") or "-"),
            str(row.get("room_number") or "-")
        ])

    table = Table(table_data, repeatRows=1)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243B64")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#EAF0F8")
        ]),
    ]))

    story.append(table)
    document.build(story)

    pdf_buffer.seek(0)

    response = make_response(pdf_buffer.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        "attachment; filename=Faculty_Timetable.pdf"
    )
    return response



@app.route("/timetable/edit/<int:timetable_id>")
@login_required
def edit_timetable(timetable_id):

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("timetable"))

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                timetable_id,
                class_id,
                subject_id,
                faculty_id,
                room_id,
                slot_id
            FROM timetable
            WHERE timetable_id = %s
        """, (timetable_id,))

        entry = cursor.fetchone()

        if not entry:
            flash("Timetable entry not found.", "error")
            return redirect(url_for("timetable"))

        cursor.execute("""
            SELECT class_id, class_name
            FROM classes
            ORDER BY class_name
        """)
        classes_data = cursor.fetchall()

        cursor.execute("""
            SELECT subject_id, subject_name
            FROM subjects
            ORDER BY subject_name
        """)
        subjects_data = cursor.fetchall()

        cursor.execute("""
            SELECT faculty_id, faculty_name
            FROM faculty
            ORDER BY faculty_name
        """)
        faculty_data = cursor.fetchall()

        cursor.execute("""
            SELECT room_id, room_number
            FROM rooms
            ORDER BY room_number
        """)
        rooms_data = cursor.fetchall()

        cursor.execute("""
            SELECT
                slot_id,
                day_of_week,
                period_number,
                start_time,
                end_time
            FROM time_slots
            ORDER BY
                FIELD(
                    day_of_week,
                    'MONDAY', 'TUESDAY', 'WEDNESDAY',
                    'THURSDAY', 'FRIDAY', 'SATURDAY'
                ),
                period_number
        """)
        slots_data = cursor.fetchall()

    except Error as error:
        print("Timetable edit loading error:", error)
        flash(f"Unable to load timetable entry: {error}", "error")
        return redirect(url_for("timetable"))

    finally:
        close_connection(connection, cursor)

    # Convert time values to strings for the template.
    for slot in slots_data:
        if slot.get("start_time") is not None:
            slot["start_time"] = str(slot["start_time"])

        if slot.get("end_time") is not None:
            slot["end_time"] = str(slot["end_time"])

    return render_template(
        "edit_timetable.html",
        entry=entry,
        classes=classes_data,
        subjects=subjects_data,
        faculty=faculty_data,
        rooms=rooms_data,
        time_slots=slots_data
    )
# ============================================================
# SAVE EDITED TIMETABLE
# ============================================================

@app.route("/timetable/edit/save", methods=["POST"])
@admin_required
def save_timetable_edit():

    timetable_id = request.form.get("timetable_id")
    class_id = request.form.get("class_id")
    subject_id = request.form.get("subject_id")
    faculty_id = request.form.get("faculty_id")
    room_id = request.form.get("room_id")
    time_slot_id = request.form.get("time_slot_id")

    if not all([
        timetable_id, class_id, subject_id,
        faculty_id, room_id, time_slot_id
    ]):
        flash("Please fill in all timetable fields.", "error")
        return redirect(url_for("timetable"))

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("timetable"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE timetable
            SET class_id = %s,
                subject_id = %s,
                faculty_id = %s,
                room_id = %s,
                time_slot_id = %s
            WHERE timetable_id = %s
        """, (
            class_id,
            subject_id,
            faculty_id,
            room_id,
            time_slot_id,
            timetable_id
        ))

        connection.commit()
        flash("Timetable entry updated successfully.", "success")

    except Error as error:
        connection.rollback()
        print("Timetable edit save error:", error)
        flash(f"Unable to update timetable: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("timetable"))


# ============================================================
# DELETE TIMETABLE ENTRY
# ============================================================

@app.route("/timetable/delete/<int:timetable_id>")
@admin_required
def delete_timetable_entry(timetable_id):

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("timetable"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM timetable
            WHERE timetable_id = %s
        """, (timetable_id,))

        deleted_rows = cursor.rowcount
        connection.commit()

        if deleted_rows > 0:
            flash("Timetable entry deleted successfully.", "success")
        else:
            flash("Timetable entry not found.", "error")

    except Error as error:
        connection.rollback()
        print("Timetable delete error:", error)
        flash(f"Unable to delete timetable entry: {error}", "error")

    finally:
        close_connection(connection, cursor)

    return redirect(url_for("timetable"))

# ============================================================
# CONFLICT CHECKER
# ============================================================

@app.route("/conflicts")
@login_required
def conflicts():

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return render_template(
            "conflicts.html",
            conflicts=[],
            faculty_conflicts=0,
            room_conflicts=0,
            class_conflicts=0,
            total_conflicts=0
        )

    cursor = connection.cursor(dictionary=True)

    faculty_conflict_count = 0
    room_conflict_count = 0
    class_conflict_count = 0
    all_conflicts = []

    try:
        # Check whether a faculty member has overlapping assignments.
        cursor.execute("""
            SELECT
                f.faculty_name AS name,
                ts.day_of_week AS day,
                ts.period_number AS period,
                ts.start_time,
                ts.end_time,
                COUNT(*) AS conflict_count
            FROM timetable t
            INNER JOIN faculty f
                ON t.faculty_id = f.faculty_id
            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id
            GROUP BY
                t.faculty_id, f.faculty_name,
                t.slot_id, ts.day_of_week,
                ts.period_number, ts.start_time, ts.end_time
            HAVING COUNT(*) > 1
        """)
        for item in cursor.fetchall():
            faculty_conflict_count += 1
            all_conflicts.append({
                "type": "Faculty",
                **item
            })

        # Check whether a room has multiple assignments.
        cursor.execute("""
            SELECT
                r.room_number AS name,
                ts.day_of_week AS day,
                ts.period_number AS period,
                ts.start_time,
                ts.end_time,
                COUNT(*) AS conflict_count
            FROM timetable t
            INNER JOIN rooms r
                ON t.room_id = r.room_id
            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id
            GROUP BY
                t.room_id, r.room_number,
                t.slot_id, ts.day_of_week,
                ts.period_number, ts.start_time, ts.end_time
            HAVING COUNT(*) > 1
        """)
        for item in cursor.fetchall():
            room_conflict_count += 1
            all_conflicts.append({
                "type": "Room",
                **item
            })

        # Check whether a class has multiple assignments.
        cursor.execute("""
            SELECT
                c.class_name AS name,
                ts.day_of_week AS day,
                ts.period_number AS period,
                ts.start_time,
                ts.end_time,
                COUNT(*) AS conflict_count
            FROM timetable t
            INNER JOIN classes c
                ON t.class_id = c.class_id
            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id
            GROUP BY
                t.class_id, c.class_name,
                t.slot_id, ts.day_of_week,
                ts.period_number, ts.start_time, ts.end_time
            HAVING COUNT(*) > 1
        """)
        for item in cursor.fetchall():
            class_conflict_count += 1
            all_conflicts.append({
                "type": "Class",
                **item
            })

    except Error as error:
        print("Conflict checker error:", error)
        flash(f"Unable to check conflicts: {error}", "error")

    finally:
        close_connection(connection, cursor)

    total_conflicts = (
        faculty_conflict_count
        + room_conflict_count
        + class_conflict_count
    )

    return render_template(
        "conflicts.html",
        conflicts=all_conflicts,
        faculty_conflicts=faculty_conflict_count,
        room_conflicts=room_conflict_count,
        class_conflicts=class_conflict_count,
        total_conflicts=total_conflicts
    )

# ============================================================
# EXPORT TIMETABLE AS PDF
# ============================================================

@app.route("/timetable/pdf")
@login_required
def timetable_pdf():

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("timetable"))

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                c.class_name,
                s.subject_name,
                s.subject_code,
                f.faculty_name,
                r.room_number,
                ts.day_of_week,
                ts.period_number,
                ts.start_time,
                ts.end_time
            FROM timetable t
            INNER JOIN classes c
                ON t.class_id = c.class_id
            INNER JOIN subjects s
                ON t.subject_id = s.subject_id
            INNER JOIN faculty f
                ON t.faculty_id = f.faculty_id
            INNER JOIN rooms r
                ON t.room_id = r.room_id
            INNER JOIN time_slots ts
    ON t.slot_id = ts.slot_id
            ORDER BY
                c.class_name,
                FIELD(
                    ts.day_of_week,
                    'MONDAY', 'TUESDAY', 'WEDNESDAY',
                    'THURSDAY', 'FRIDAY', 'SATURDAY'
                ),
                ts.period_number
        """)

        timetable_data = cursor.fetchall()

    except Error as error:
        print("PDF timetable query error:", error)
        flash(f"Unable to create PDF: {error}", "error")
        return redirect(url_for("timetable"))

    finally:
        close_connection(connection, cursor)

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()

    title = Paragraph(
        "Faculty Automatic Timetable",
        styles["Title"]
    )

    subtitle = Paragraph(
        "Generated Timetable",
        styles["Heading2"]
    )

    data = [[
        "Class", "Subject", "Code", "Faculty",
        "Room", "Day", "Period", "Start", "End"
    ]]

    for row in timetable_data:
        data.append([
            str(row.get("class_name", "")),
            str(row.get("subject_name", "")),
            str(row.get("subject_code", "")),
            str(row.get("faculty_name", "")),
            str(row.get("room_number", "")),
            str(row.get("day_of_week", "")),
            str(row.get("period_number", "")),
            str(row.get("start_time", "")),
            str(row.get("end_time", ""))
        ])

    table = Table(data, repeatRows=1)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0),
         colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f3f4f6")])
    ]))

    document.build([title, subtitle, table])

    pdf_data = buffer.getvalue()
    buffer.close()

    response = make_response(pdf_data)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        "attachment; filename=faculty_timetable.pdf"
    )

    return response


# ============================================================
# EMAIL AND PASSWORD RESET HELPERS
# ============================================================

def send_reset_email(recipient, reset_url):
    message = EmailMessage()
    message["Subject"] = "Faculty Timetable Generator - Password Reset"
    message["From"] = os.environ["MAIL_FROM"]
    message["To"] = recipient

    message.set_content(
        "A password reset was requested for your account.\n\n"
        f"Use this link to reset your password:\n{reset_url}\n\n"
        "This link expires in 15 minutes and can be used once.\n"
        "If you did not request this, ignore this email."
    )

    with smtplib.SMTP(
        os.environ.get("MAIL_HOST", "smtp.gmail.com"),
        int(os.environ.get("MAIL_PORT", "587")),
        timeout=20
    ) as server:
        server.starttls()
        server.login(
            os.environ["MAIL_USERNAME"],
            os.environ["MAIL_PASSWORD"]
        )
        server.send_message(message)


def close_auth_resources(connection, cursor):
    if cursor is not None:
        cursor.close()
    if connection is not None:
        connection.close()


# ============================================================
# SIGN UP
# ============================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if len(username) < 3 or len(username) > 50:
        flash("Username must be between 3 and 50 characters.", "error")
        return redirect(url_for("signup"))

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        flash("Enter a valid email address.", "error")
        return redirect(url_for("signup"))

    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "error")
        return redirect(url_for("signup"))

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("signup"))

    connection = get_connection()
    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("signup"))

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT user_id FROM users WHERE username = %s OR email = %s",
            (username, email)
        )

        if cursor.fetchone():
            flash("Username or email is already registered.", "error")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            """,
            (username, email, password_hash, "STAFF")
        )
        connection.commit()

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))

    except Error as error:
        connection.rollback()
        print("Signup error:", error)
        flash("Unable to create the account. Please try again.", "error")
        return redirect(url_for("signup"))

    finally:
        close_auth_resources(connection, cursor)


# ============================================================
# FORGOT PASSWORD
# ============================================================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    email = request.form.get("email", "").strip().lower()

    if not email:
        flash("Please enter your registered email address.", "error")
        return redirect(url_for("forgot_password"))

    connection = get_connection()
    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("forgot_password"))

    cursor = None
    reset_url = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, email FROM users WHERE email = %s",
            (email,)
        )
        user = cursor.fetchone()

        if user:
            # Invalidate older, unused reset links for this account.
            cursor.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = NOW()
                WHERE user_id = %s AND used_at IS NULL
                """,
                (user["user_id"],)
            )

            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(
                raw_token.encode("utf-8")
            ).hexdigest()

            expires_at = datetime.now() + timedelta(minutes=15)

            cursor.execute(
                """
                INSERT INTO password_reset_tokens
                    (user_id, token_hash, expires_at)
                VALUES (%s, %s, %s)
                """,
                (user["user_id"], token_hash, expires_at)
            )
            connection.commit()

            base_url = os.environ.get(
                "RESET_BASE_URL", "http://127.0.0.1:5000"
            ).rstrip("/")

            reset_url = (
                f"{base_url}/reset-password/{raw_token}"
            )

    except Error as error:
        connection.rollback()
        print("Forgot password database error:", error)
        flash("Unable to process your request. Please try again.", "error")
        return redirect(url_for("forgot_password"))

    finally:
        close_auth_resources(connection, cursor)

    if reset_url:
        try:
            send_reset_email(email, reset_url)
        except Exception as error:
            print("Reset email error:", error)
            flash(
                "We couldn't send the email. Check your mail configuration "
                "and try again.",
                "error"
            )
            return redirect(url_for("forgot_password"))

    # Do not reveal whether an email address has an account.
    flash(
        "If that email is registered, a password-reset link will be sent.",
        "info"
    )
    return redirect(url_for("login"))


# ============================================================
# RESET PASSWORD
# ============================================================

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    connection = get_connection()
    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("login"))

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT id, user_id, expires_at, used_at
            FROM password_reset_tokens
            WHERE token_hash = %s
            """,
            (token_hash,)
        )
        reset_record = cursor.fetchone()

        if (
            not reset_record
            or reset_record["used_at"] is not None
            or reset_record["expires_at"] <= datetime.now()
        ):
            flash(
                "This reset link is invalid, expired, or already used.",
                "error"
            )
            return redirect(url_for("forgot_password"))

        if request.method == "GET":
            return render_template("reset_password.html", token=token)

        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return render_template("reset_password.html", token=token)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)

        # Recheck and consume the token atomically.
        cursor.execute(
            """
            UPDATE password_reset_tokens
            SET used_at = NOW()
            WHERE id = %s
              AND used_at IS NULL
              AND expires_at > NOW()
            """,
            (reset_record["id"],)
        )

        if cursor.rowcount != 1:
            connection.rollback()
            flash("This reset link has expired or was already used.", "error")
            return redirect(url_for("forgot_password"))

        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
            """,
            (
                generate_password_hash(password),
                reset_record["user_id"]
            )
        )

        connection.commit()
        flash("Password reset successfully. Please log in.", "success")
        return redirect(url_for("login"))

    except Error as error:
        connection.rollback()
        print("Password reset error:", error)
        flash("Unable to reset the password. Please try again.", "error")
        return redirect(url_for("forgot_password"))

    finally:
        close_auth_resources(connection, cursor)


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
    
            
