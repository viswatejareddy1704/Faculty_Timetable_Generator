CREATE DATABASE IF NOT EXISTS faculty_timetable_db;

USE faculty_timetable_db;


-- =====================================================
-- 1. USERS
-- =====================================================

CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('ADMIN', 'STAFF') DEFAULT 'STAFF',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- 2. DEPARTMENTS
-- =====================================================

CREATE TABLE IF NOT EXISTS departments (
    department_id INT AUTO_INCREMENT PRIMARY KEY,
    department_name VARCHAR(150) NOT NULL UNIQUE,
    department_code VARCHAR(20) NOT NULL UNIQUE
);


-- =====================================================
-- 3. FACULTY
-- =====================================================

CREATE TABLE IF NOT EXISTS faculty (
    faculty_id INT AUTO_INCREMENT PRIMARY KEY,
    faculty_name VARCHAR(150) NOT NULL,
    employee_id VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(150) UNIQUE,
    phone VARCHAR(20),
    designation VARCHAR(100),
    department_id INT,
    max_classes_per_day INT DEFAULT 4,

    FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        ON DELETE SET NULL
);


-- =====================================================
-- 4. SUBJECTS
-- =====================================================

CREATE TABLE IF NOT EXISTS subjects (
    subject_id INT AUTO_INCREMENT PRIMARY KEY,
    subject_code VARCHAR(50) NOT NULL UNIQUE,
    subject_name VARCHAR(150) NOT NULL,
    subject_type ENUM('THEORY', 'LAB') DEFAULT 'THEORY',
    weekly_hours INT NOT NULL DEFAULT 3,
    department_id INT,

    FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        ON DELETE SET NULL
);


-- =====================================================
-- 5. CLASSES / SECTIONS
-- =====================================================

CREATE TABLE IF NOT EXISTS classes (
    class_id INT AUTO_INCREMENT PRIMARY KEY,
    class_name VARCHAR(100) NOT NULL,
    year INT NOT NULL,
    section VARCHAR(20) NOT NULL,
    semester INT NOT NULL,
    department_id INT,

    FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        ON DELETE SET NULL
);


-- =====================================================
-- 6. ROOMS
-- =====================================================

CREATE TABLE IF NOT EXISTS rooms (
    room_id INT AUTO_INCREMENT PRIMARY KEY,
    room_number VARCHAR(50) NOT NULL UNIQUE,
    room_type ENUM('CLASSROOM', 'LAB', 'SEMINAR_HALL') DEFAULT 'CLASSROOM',
    capacity INT DEFAULT 60,
    building VARCHAR(100)
);


-- =====================================================
-- 7. TIME SLOTS
-- =====================================================

CREATE TABLE IF NOT EXISTS time_slots (
    slot_id INT AUTO_INCREMENT PRIMARY KEY,
    day_of_week ENUM(
        'MONDAY',
        'TUESDAY',
        'WEDNESDAY',
        'THURSDAY',
        'FRIDAY',
        'SATURDAY'
    ) NOT NULL,

    period_number INT NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,

    UNIQUE(day_of_week, period_number)
);


-- =====================================================
-- 8. FACULTY AVAILABILITY
-- =====================================================

CREATE TABLE IF NOT EXISTS faculty_availability (
    availability_id INT AUTO_INCREMENT PRIMARY KEY,
    faculty_id INT NOT NULL,
    slot_id INT NOT NULL,
    is_available BOOLEAN DEFAULT TRUE,

    FOREIGN KEY (faculty_id)
        REFERENCES faculty(faculty_id)
        ON DELETE CASCADE,

    FOREIGN KEY (slot_id)
        REFERENCES time_slots(slot_id)
        ON DELETE CASCADE,

    UNIQUE(faculty_id, slot_id)
);


-- =====================================================
-- 9. SUBJECT - FACULTY
-- =====================================================

CREATE TABLE IF NOT EXISTS subject_faculty (
    subject_faculty_id INT AUTO_INCREMENT PRIMARY KEY,
    subject_id INT NOT NULL,
    faculty_id INT NOT NULL,

    FOREIGN KEY (subject_id)
        REFERENCES subjects(subject_id)
        ON DELETE CASCADE,

    FOREIGN KEY (faculty_id)
        REFERENCES faculty(faculty_id)
        ON DELETE CASCADE,

    UNIQUE(subject_id, faculty_id)
);


-- =====================================================
-- 10. CLASS - SUBJECT
-- =====================================================

CREATE TABLE IF NOT EXISTS class_subjects (
    class_subject_id INT AUTO_INCREMENT PRIMARY KEY,
    class_id INT NOT NULL,
    subject_id INT NOT NULL,
    weekly_hours INT NOT NULL DEFAULT 3,

    FOREIGN KEY (class_id)
        REFERENCES classes(class_id)
        ON DELETE CASCADE,

    FOREIGN KEY (subject_id)
        REFERENCES subjects(subject_id)
        ON DELETE CASCADE,

    UNIQUE(class_id, subject_id)
);


-- =====================================================
-- 11. TIMETABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS timetable (
    timetable_id INT AUTO_INCREMENT PRIMARY KEY,

    class_id INT NOT NULL,
    subject_id INT NOT NULL,
    faculty_id INT NOT NULL,
    room_id INT NOT NULL,
    slot_id INT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (class_id)
        REFERENCES classes(class_id)
        ON DELETE CASCADE,

    FOREIGN KEY (subject_id)
        REFERENCES subjects(subject_id)
        ON DELETE CASCADE,

    FOREIGN KEY (faculty_id)
        REFERENCES faculty(faculty_id)
        ON DELETE CASCADE,

    FOREIGN KEY (room_id)
        REFERENCES rooms(room_id)
        ON DELETE CASCADE,

    FOREIGN KEY (slot_id)
        REFERENCES time_slots(slot_id)
        ON DELETE CASCADE
);