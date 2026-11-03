from database.db import get_connection


def empty_result(message=""):
    return {
        "success": False,
        "message": message,
        "total_conflicts": 0,

        "faculty_conflicts": [],
        "class_conflicts": [],
        "room_conflicts": [],
        "availability_conflicts": [],
        "room_type_conflicts": [],
        "duplicate_conflicts": [],

        "total_timetable_entries": 0
    }


def check_timetable_conflicts():

    connection = get_connection()

    if connection is None:
        return empty_result(
            "Unable to connect to the database."
        )

    cursor = connection.cursor(dictionary=True)

    result = {
        "success": True,
        "message": "Timetable checked successfully.",
        "total_conflicts": 0,

        "faculty_conflicts": [],
        "class_conflicts": [],
        "room_conflicts": [],
        "availability_conflicts": [],
        "room_type_conflicts": [],
        "duplicate_conflicts": [],

        "total_timetable_entries": 0
    }

    try:

        # =========================================================
        # TOTAL TIMETABLE ENTRIES
        # =========================================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM timetable
        """)

        row = cursor.fetchone()

        result["total_timetable_entries"] = row["total"]


        # =========================================================
        # 1. FACULTY CLASHES
        #
        # Same faculty cannot teach two classes
        # at the same time.
        # =========================================================

        cursor.execute("""
            SELECT
                t.slot_id,
                ts.day_of_week,
                ts.period_number,
                ts.start_time,
                ts.end_time,

                t.faculty_id,
                f.faculty_name,

                COUNT(*) AS conflict_count

            FROM timetable t

            INNER JOIN faculty f
                ON t.faculty_id = f.faculty_id

            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id

            GROUP BY
                t.slot_id,
                ts.day_of_week,
                ts.period_number,
                ts.start_time,
                ts.end_time,
                t.faculty_id,
                f.faculty_name

            HAVING COUNT(*) > 1

            ORDER BY
                FIELD(
                    ts.day_of_week,
                    'MONDAY',
                    'TUESDAY',
                    'WEDNESDAY',
                    'THURSDAY',
                    'FRIDAY',
                    'SATURDAY'
                ),
                ts.period_number
        """)

        result["faculty_conflicts"] = cursor.fetchall()


        # =========================================================
        # 2. CLASS CLASHES
        #
        # Same class cannot have two subjects
        # at the same time.
        # =========================================================

        cursor.execute("""
            SELECT
                t.slot_id,

                ts.day_of_week,
                ts.period_number,

                t.class_id,

                c.class_name,
                c.section,
                c.semester,

                COUNT(*) AS conflict_count

            FROM timetable t

            INNER JOIN classes c
                ON t.class_id = c.class_id

            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id

            GROUP BY
                t.slot_id,
                ts.day_of_week,
                ts.period_number,
                t.class_id,
                c.class_name,
                c.section,
                c.semester

            HAVING COUNT(*) > 1

            ORDER BY
                FIELD(
                    ts.day_of_week,
                    'MONDAY',
                    'TUESDAY',
                    'WEDNESDAY',
                    'THURSDAY',
                    'FRIDAY',
                    'SATURDAY'
                ),
                ts.period_number
        """)

        result["class_conflicts"] = cursor.fetchall()


        # =========================================================
        # 3. ROOM CLASHES
        #
        # Same room cannot be used by two classes
        # at the same time.
        # =========================================================

        cursor.execute("""
            SELECT
                t.slot_id,

                ts.day_of_week,
                ts.period_number,

                t.room_id,
                r.room_number,

                COUNT(*) AS conflict_count

            FROM timetable t

            INNER JOIN rooms r
                ON t.room_id = r.room_id

            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id

            GROUP BY
                t.slot_id,
                ts.day_of_week,
                ts.period_number,
                t.room_id,
                r.room_number

            HAVING COUNT(*) > 1

            ORDER BY
                FIELD(
                    ts.day_of_week,
                    'MONDAY',
                    'TUESDAY',
                    'WEDNESDAY',
                    'THURSDAY',
                    'FRIDAY',
                    'SATURDAY'
                ),
                ts.period_number
        """)

        result["room_conflicts"] = cursor.fetchall()


        # =========================================================
        # 4. FACULTY AVAILABILITY
        #
        # Faculty should not be scheduled in a slot
        # marked unavailable.
        # =========================================================

        cursor.execute("""
            SELECT
                t.timetable_id,

                ts.day_of_week,
                ts.period_number,
                ts.start_time,
                ts.end_time,

                f.faculty_name,

                s.subject_code,
                s.subject_name,

                fa.is_available

            FROM timetable t

            INNER JOIN faculty f
                ON t.faculty_id = f.faculty_id

            INNER JOIN subjects s
                ON t.subject_id = s.subject_id

            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id

            INNER JOIN faculty_availability fa
                ON fa.faculty_id = t.faculty_id
                AND fa.slot_id = t.slot_id

            WHERE fa.is_available = FALSE

            ORDER BY
                FIELD(
                    ts.day_of_week,
                    'MONDAY',
                    'TUESDAY',
                    'WEDNESDAY',
                    'THURSDAY',
                    'FRIDAY',
                    'SATURDAY'
                ),
                ts.period_number
        """)

        result["availability_conflicts"] = cursor.fetchall()


        # =========================================================
        # 5. ROOM TYPE CONFLICTS
        #
        # LAB subject -> LAB room
        # THEORY subject -> CLASSROOM / SEMINAR_HALL
        # =========================================================

        cursor.execute("""
            SELECT

                t.timetable_id,

                ts.day_of_week,
                ts.period_number,

                c.class_name,
                c.section,

                s.subject_code,
                s.subject_name,
                s.subject_type,

                r.room_number,
                r.room_type

            FROM timetable t

            INNER JOIN subjects s
                ON t.subject_id = s.subject_id

            INNER JOIN rooms r
                ON t.room_id = r.room_id

            INNER JOIN classes c
                ON t.class_id = c.class_id

            INNER JOIN time_slots ts
                ON t.slot_id = ts.slot_id

            WHERE

                (
                    s.subject_type = 'LAB'
                    AND r.room_type <> 'LAB'
                )

                OR

                (
                    s.subject_type = 'THEORY'
                    AND r.room_type = 'LAB'
                )

            ORDER BY
                t.timetable_id
        """)

        result["room_type_conflicts"] = cursor.fetchall()


        # =========================================================
        # 6. DUPLICATE ENTRIES
        # =========================================================

        cursor.execute("""
            SELECT

                class_id,
                subject_id,
                faculty_id,
                room_id,
                slot_id,

                COUNT(*) AS duplicate_count

            FROM timetable

            GROUP BY
                class_id,
                subject_id,
                faculty_id,
                room_id,
                slot_id

            HAVING COUNT(*) > 1
        """)

        result["duplicate_conflicts"] = cursor.fetchall()


        # =========================================================
        # TOTAL CONFLICTS
        # =========================================================

        result["total_conflicts"] = (

            len(result["faculty_conflicts"])

            + len(result["class_conflicts"])

            + len(result["room_conflicts"])

            + len(result["availability_conflicts"])

            + len(result["room_type_conflicts"])

            + len(result["duplicate_conflicts"])

        )


        # =========================================================
        # FINAL MESSAGE
        # =========================================================

        if result["total_conflicts"] == 0:

            result["message"] = (
                "Timetable is conflict-free."
            )

        else:

            result["message"] = (
                f"{result['total_conflicts']} "
                f"conflict(s) found."
            )


        return result


    except Exception as error:

        print(
            "Conflict checker error:",
            error
        )

        result["success"] = False

        result["message"] = (
            f"Conflict checker error: {error}"
        )

        return result


    finally:

        cursor.close()
        connection.close()