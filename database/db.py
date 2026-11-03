import mysql.connector
from mysql.connector import Error

from config import Config


def get_connection():
    try:
        connection = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            port=Config.DB_PORT
        )

        if connection.is_connected():
            return connection

    except Error as error:
        print(f"Database connection error: {error}")

    return None


def get_count(table_name):
    connection = get_connection()

    if connection is None:
        return 0

    try:
        cursor = connection.cursor()

        allowed_tables = {
            "faculty",
            "subjects",
            "classes",
            "rooms",
            "departments",
            "time_slots"
        }

        if table_name not in allowed_tables:
            return 0

        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        )

        result = cursor.fetchone()

        return result[0]

    except Error as error:
        print(f"Database query error: {error}")
        return 0

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()