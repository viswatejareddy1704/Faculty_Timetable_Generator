USE faculty_timetable_db;

-- =====================================================
-- DEPARTMENTS
-- =====================================================

INSERT INTO departments
(department_name, department_code)
VALUES
('Computer Science and Engineering', 'CSE'),
('Electronics and Communication Engineering', 'ECE');


-- =====================================================
-- FACULTY
-- =====================================================

INSERT INTO faculty
(faculty_name, employee_id, email, phone, designation, department_id, max_classes_per_day)
VALUES
('Dr. Anil Kumar', 'FAC001', 'anil@example.com', '9000000001',
 'Professor', 1, 4),

('Dr. Priya Sharma', 'FAC002', 'priya@example.com', '9000000002',
 'Associate Professor', 1, 4),

('Mr. Rahul Reddy', 'FAC003', 'rahul@example.com', '9000000003',
 'Assistant Professor', 1, 4),

('Ms. Sneha Rao', 'FAC004', 'sneha@example.com', '9000000004',
 'Assistant Professor', 1, 4),

('Dr. Kiran Kumar', 'FAC005', 'kiran@example.com', '9000000005',
 'Professor', 2, 4);


-- =====================================================
-- SUBJECTS
-- =====================================================

INSERT INTO subjects
(subject_code, subject_name, subject_type, weekly_hours, department_id)
VALUES
('CS301', 'Data Structures', 'THEORY', 4, 1),
('CS302', 'Database Management Systems', 'THEORY', 4, 1),
('CS303', 'Operating Systems', 'THEORY', 4, 1),
('CS304', 'Computer Networks', 'THEORY', 3, 1),
('CS305', 'Data Structures Lab', 'LAB', 2, 1),
('CS306', 'DBMS Lab', 'LAB', 2, 1),
('CS307', 'Artificial Intelligence', 'THEORY', 3, 1),
('EC301', 'Digital Electronics', 'THEORY', 4, 2);


-- =====================================================
-- CLASSES
-- =====================================================

INSERT INTO classes
(class_name, year, section, semester, department_id)
VALUES
('B.Tech CSE', 3, 'A', 5, 1),
('B.Tech CSE', 3, 'B', 5, 1),
('B.Tech CSE', 4, 'A', 7, 1),
('B.Tech ECE', 3, 'A', 5, 2);


-- =====================================================
-- ROOMS
-- =====================================================

INSERT INTO rooms
(room_number, room_type, capacity, building)
VALUES
('CSE-101', 'CLASSROOM', 60, 'CSE Block'),
('CSE-102', 'CLASSROOM', 60, 'CSE Block'),
('CSE-103', 'CLASSROOM', 60, 'CSE Block'),
('LAB-201', 'LAB', 40, 'CSE Block'),
('LAB-202', 'LAB', 40, 'CSE Block'),
('ECE-101', 'CLASSROOM', 60, 'ECE Block'),
('SEM-001', 'SEMINAR_HALL', 100, 'Main Block');


-- =====================================================
-- TIME SLOTS
-- =====================================================

INSERT INTO time_slots
(day_of_week, period_number, start_time, end_time)
VALUES
('MONDAY', 1, '09:00:00', '10:00:00'),
('MONDAY', 2, '10:00:00', '11:00:00'),
('MONDAY', 3, '11:15:00', '12:15:00'),
('MONDAY', 4, '12:15:00', '13:15:00'),
('MONDAY', 5, '14:00:00', '15:00:00'),
('MONDAY', 6, '15:00:00', '16:00:00'),

('TUESDAY', 1, '09:00:00', '10:00:00'),
('TUESDAY', 2, '10:00:00', '11:00:00'),
('TUESDAY', 3, '11:15:00', '12:15:00'),
('TUESDAY', 4, '12:15:00', '13:15:00'),
('TUESDAY', 5, '14:00:00', '15:00:00'),
('TUESDAY', 6, '15:00:00', '16:00:00'),

('WEDNESDAY', 1, '09:00:00', '10:00:00'),
('WEDNESDAY', 2, '10:00:00', '11:00:00'),
('WEDNESDAY', 3, '11:15:00', '12:15:00'),
('WEDNESDAY', 4, '12:15:00', '13:15:00'),
('WEDNESDAY', 5, '14:00:00', '15:00:00'),
('WEDNESDAY', 6, '15:00:00', '16:00:00'),

('THURSDAY', 1, '09:00:00', '10:00:00'),
('THURSDAY', 2, '10:00:00', '11:00:00'),
('THURSDAY', 3, '11:15:00', '12:15:00'),
('THURSDAY', 4, '12:15:00', '13:15:00'),
('THURSDAY', 5, '14:00:00', '15:00:00'),
('THURSDAY', 6, '15:00:00', '16:00:00'),

('FRIDAY', 1, '09:00:00', '10:00:00'),
('FRIDAY', 2, '10:00:00', '11:00:00'),
('FRIDAY', 3, '11:15:00', '12:15:00'),
('FRIDAY', 4, '12:15:00', '13:15:00'),
('FRIDAY', 5, '14:00:00', '15:00:00'),
('FRIDAY', 6, '15:00:00', '16:00:00'),

('SATURDAY', 1, '09:00:00', '10:00:00'),
('SATURDAY', 2, '10:00:00', '11:00:00'),
('SATURDAY', 3, '11:15:00', '12:15:00'),
('SATURDAY', 4, '12:15:00', '13:15:00'),
('SATURDAY', 5, '14:00:00', '15:00:00'),
('SATURDAY', 6, '15:00:00', '16:00:00');


-- =====================================================
-- SUBJECT - FACULTY
-- =====================================================

INSERT INTO subject_faculty
(subject_id, faculty_id)
VALUES
(1, 1),
(2, 2),
(3, 3),
(4, 4),
(5, 1),
(6, 2),
(7, 3),
(8, 5);


-- =====================================================
-- CLASS - SUBJECT
-- =====================================================

INSERT INTO class_subjects
(class_id, subject_id, weekly_hours)
VALUES
(1, 1, 4),
(1, 2, 4),
(1, 3, 4),
(1, 4, 3),
(1, 5, 2),
(1, 6, 2),
(1, 7, 3),

(2, 1, 4),
(2, 2, 4),
(2, 3, 4),
(2, 4, 3),
(2, 5, 2),
(2, 6, 2),

(3, 7, 3),
(3, 4, 3),

(4, 8, 4);