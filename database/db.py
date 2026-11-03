import mysql.connector
from mysql.connector import Error

from config import Config


def get_connection():
    try:
        connection_config = {
            "host": Config.DB_HOST,
            "user": Config.DB_USER,
            "password": Config.DB_PASSWORD,
            "database": Config.DB_NAME,
            "port": Config.DB_PORT
        }

        # Enable certificate verification when an SSL certificate is configured
        if Config.DB_SSL_CA:
            connection_config.update({
                "ssl_ca": Config.DB_SSL_CA,
                "ssl_verify_cert": True,
                "ssl_verify_identity": True
            })

        connection = mysql.connector.connect(**connection_config)

        if connection.is_connected():
            return connection

    except Error as error:
        print(f"Database connection error: {error}")

    return None


def get_count(table_name):
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

    connection = get_connection()

    if connection is None:
        return 0

    cursor = None

    try:
        cursor = connection.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        result = cursor.fetchone()
        return result[0]

    except Error as error:
        print(f"Database query error: {error}")
        return 0

    finally:
        if cursor is not None:
            cursor.close()

        connection.close()