import mysql.connector
from ortools.sat.python import cp_model

from config import Config


def get_connection():
    """Create a MySQL database connection."""
    return mysql.connector.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        port=Config.DB_PORT
    )


def generate_timetable():
    """
    Generate a weekly timetable using Google OR-Tools CP-SAT.

    Hard constraints:
    1. A class cannot have two subjects in the same slot.
    2. A faculty member cannot teach two classes in the same slot.
    3. A room cannot be used by two classes in the same slot.
    4. Faculty availability is respected.
    5. Lab subjects are assigned only to labs.
    6. Theory subjects are assigned only to classrooms/seminar halls.
    7. Every required weekly subject hour is scheduled.

    Returns:
        (success, message, count)
    """

    connection = None
    cursor = None

    try:
        # 1. Connect to the database
        connection = get_connection()

        if connection is None or not connection.is_connected():
            return False, "Could not connect to database.", 0

        cursor = connection.cursor(dictionary=True)

        # 2. Get classes and their subject assignments
        cursor.execute("""
            SELECT
                cs.class_subject_id,
                cs.class_id,
                cs.subject_id,
                cs.weekly_hours,
                c.class_name,
                s.subject_code,
                s.subject_name,
                s.subject_type
            FROM class_subjects cs
            JOIN classes c
                ON cs.class_id = c.class_id
            JOIN subjects s
                ON cs.subject_id = s.subject_id
            ORDER BY cs.class_id, cs.subject_id
        """)

        assignments = cursor.fetchall()

        if not assignments:
            return False, "No class-subject assignments found.", 0

        # 3. Get subject-faculty assignments
        cursor.execute("""
            SELECT
                sf.subject_id,
                sf.faculty_id,
                f.faculty_name
            FROM subject_faculty sf
            JOIN faculty f
                ON sf.faculty_id = f.faculty_id
        """)

        subject_faculty_rows = cursor.fetchall()
        subject_faculty = {}

        for row in subject_faculty_rows:
            subject_id = row["subject_id"]

            if subject_id not in subject_faculty:
                subject_faculty[subject_id] = []

            subject_faculty[subject_id].append(row["faculty_id"])

        # 4. Get available timetable slots
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
                    'MONDAY',
                    'TUESDAY',
                    'WEDNESDAY',
                    'THURSDAY',
                    'FRIDAY',
                    'SATURDAY'
                ),
                period_number
        """)

        slots = cursor.fetchall()

        if not slots:
            return False, "No time slots found.", 0

        # 5. Get rooms
        cursor.execute("""
            SELECT
                room_id,
                room_number,
                room_type,
                capacity
            FROM rooms
            ORDER BY room_id
        """)

        rooms = cursor.fetchall()

        if not rooms:
            return False, "No rooms found.", 0

        # 6. Get faculty availability
        cursor.execute("""
            SELECT
                faculty_id,
                slot_id,
                is_available
            FROM faculty_availability
        """)

        availability_rows = cursor.fetchall()
        faculty_availability = {}

        for row in availability_rows:
            key = (row["faculty_id"], row["slot_id"])
            faculty_availability[key] = bool(row["is_available"])

        # 7. Create one lesson for every required weekly hour
        lessons = []
        lesson_id = 0

        for assignment in assignments:
            weekly_hours = int(assignment["weekly_hours"])

            if weekly_hours <= 0:
                continue

            subject_id = assignment["subject_id"]
            available_faculty = subject_faculty.get(subject_id, [])

            if not available_faculty:
                return (
                    False,
                    f"No faculty assigned to subject "
                    f"{assignment['subject_code']} - "
                    f"{assignment['subject_name']}.",
                    0
                )

            for hour_number in range(weekly_hours):
                lessons.append({
                    "lesson_id": lesson_id,
                    "class_id": assignment["class_id"],
                    "class_name": assignment["class_name"],
                    "subject_id": assignment["subject_id"],
                    "subject_code": assignment["subject_code"],
                    "subject_name": assignment["subject_name"],
                    "subject_type": assignment["subject_type"],
                    "faculty_ids": available_faculty,
                    "hour_number": hour_number + 1
                })

                lesson_id += 1

        if not lessons:
            return False, "No lessons were created.", 0

        # 8. Check room compatibility
        def room_is_valid(subject_type, room):
            if str(subject_type).upper() == "LAB":
                return str(room["room_type"]).upper() == "LAB"

            return str(room["room_type"]).upper() in (
                "CLASSROOM",
                "SEMINAR_HALL"
            )

        # 9. Check faculty availability
        def faculty_is_available(faculty_id, slot_id):
            key = (faculty_id, slot_id)

            # Respect explicitly recorded availability.
            # If no record exists, assume the faculty is available.
            return faculty_availability.get(key, True)

        # 10. Build the CP-SAT model
        model = cp_model.CpModel()

        # Key: (lesson_id, slot_id, faculty_id, room_id)
        choice_vars = {}
        lesson_candidates = {}

        for lesson in lessons:
            current_lesson_id = lesson["lesson_id"]
            candidates = []

            for slot in slots:
                slot_id = slot["slot_id"]

                for faculty_id in lesson["faculty_ids"]:
                    if not faculty_is_available(faculty_id, slot_id):
                        continue

                    for room in rooms:
                        room_id = room["room_id"]

                        if not room_is_valid(lesson["subject_type"], room):
                            continue

                        key = (
                            current_lesson_id,
                            slot_id,
                            faculty_id,
                            room_id
                        )

                        variable = model.NewBoolVar(
                            f"x_{current_lesson_id}_{slot_id}_"
                            f"{faculty_id}_{room_id}"
                        )

                        choice_vars[key] = variable
                        candidates.append(key)

            if not candidates:
                return (
                    False,
                    f"No valid slot, faculty and room combination "
                    f"for {lesson['class_name']} - "
                    f"{lesson['subject_name']}.",
                    0
                )

            lesson_candidates[current_lesson_id] = candidates

            # Every lesson must be scheduled exactly once.
            model.Add(
                sum(choice_vars[key] for key in candidates) == 1
            )

        # 11. Class clash constraint
        class_ids = {lesson["class_id"] for lesson in lessons}
        slot_ids = [slot["slot_id"] for slot in slots]

        for class_id in class_ids:
            for slot_id in slot_ids:
                variables = []

                for lesson in lessons:
                    if lesson["class_id"] != class_id:
                        continue

                    for key in lesson_candidates[lesson["lesson_id"]]:
                        if key[1] == slot_id:
                            variables.append(choice_vars[key])

                if variables:
                    model.Add(sum(variables) <= 1)

        # 12. Faculty clash constraint
        faculty_ids = {
            faculty_id
            for lesson in lessons
            for faculty_id in lesson["faculty_ids"]
        }

        for faculty_id in faculty_ids:
            for slot_id in slot_ids:
                variables = []

                for lesson in lessons:
                    for key in lesson_candidates[lesson["lesson_id"]]:
                        if key[1] == slot_id and key[2] == faculty_id:
                            variables.append(choice_vars[key])

                if variables:
                    model.Add(sum(variables) <= 1)

        # 13. Room clash constraint
        room_ids = [room["room_id"] for room in rooms]

        for room_id in room_ids:
            for slot_id in slot_ids:
                variables = []

                for lesson in lessons:
                    for key in lesson_candidates[lesson["lesson_id"]]:
                        if key[1] == slot_id and key[3] == room_id:
                            variables.append(choice_vars[key])

                if variables:
                    model.Add(sum(variables) <= 1)

        # 14. Soft constraint:
        # Avoid repeating the same subject on the same day.
        penalty_variables = []
        slots_by_day = {}

        for slot in slots:
            day = slot["day_of_week"]
            slots_by_day.setdefault(day, []).append(slot["slot_id"])

        for index, lesson_a in enumerate(lessons):
            for lesson_b in lessons[index + 1:]:
                if lesson_a["class_id"] != lesson_b["class_id"]:
                    continue

                if lesson_a["subject_id"] != lesson_b["subject_id"]:
                    continue

                for day, day_slot_ids in slots_by_day.items():
                    same_day_vars = []

                    for slot_a in day_slot_ids:
                        for slot_b in day_slot_ids:
                            if slot_a == slot_b:
                                continue

                            for key_a in lesson_candidates[lesson_a["lesson_id"]]:
                                if key_a[1] != slot_a:
                                    continue

                                for key_b in lesson_candidates[lesson_b["lesson_id"]]:
                                    if key_b[1] != slot_b:
                                        continue

                                    both = model.NewBoolVar(
                                        f"same_day_{lesson_a['lesson_id']}_"
                                        f"{lesson_b['lesson_id']}_"
                                        f"{slot_a}_{slot_b}"
                                    )

                                    model.AddMultiplicationEquality(
                                        both,
                                        [choice_vars[key_a], choice_vars[key_b]]
                                    )

                                    same_day_vars.append(both)

                    if same_day_vars:
                        penalty = model.NewBoolVar(
                            f"penalty_{lesson_a['lesson_id']}_"
                            f"{lesson_b['lesson_id']}_{day}"
                        )

                        model.AddMaxEquality(penalty, same_day_vars)
                        penalty_variables.append(penalty)

        # 15. Minimize repeated subjects on the same day
        if penalty_variables:
            model.Minimize(sum(penalty_variables))

        # 16. Solve the model
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60
        solver.parameters.num_search_workers = 8

        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return (
                False,
                "OR-Tools could not find a feasible timetable. "
                "Check faculty assignments, availability, rooms "
                "and weekly hours.",
                0
            )

        # 17. Extract the solution
        generated_rows = []

        for lesson in lessons:
            current_lesson_id = lesson["lesson_id"]
            selected = None

            for key in lesson_candidates[current_lesson_id]:
                if solver.Value(choice_vars[key]) == 1:
                    selected = key
                    break

            if selected is None:
                return (
                    False,
                    f"Could not extract timetable entry for "
                    f"{lesson['subject_name']}.",
                    0
                )

            _, slot_id, faculty_id, room_id = selected

            generated_rows.append({
                "class_id": lesson["class_id"],
                "subject_id": lesson["subject_id"],
                "faculty_id": faculty_id,
                "room_id": room_id,
                "slot_id": slot_id
            })

        # 18. Replace old timetable entries with the new schedule.
        # Do not commit until all inserts succeed.
        cursor.execute("DELETE FROM timetable")

        insert_query = """
            INSERT INTO timetable
                (class_id, subject_id, faculty_id, room_id, slot_id)
            VALUES (%s, %s, %s, %s, %s)
        """

        for row in generated_rows:
            cursor.execute(
                insert_query,
                (
                    row["class_id"],
                    row["subject_id"],
                    row["faculty_id"],
                    row["room_id"],
                    row["slot_id"]
                )
            )

        connection.commit()

        return (
            True,
            f"Timetable generated successfully with "
            f"{len(generated_rows)} scheduled periods.",
            len(generated_rows)
        )

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        print(f"Timetable generation error: {error}")

        return (
            False,
            f"Timetable generation error: {error}",
            0
        )

    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass

        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

