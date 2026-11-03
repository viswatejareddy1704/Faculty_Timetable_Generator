
import os
from pathlib import Path

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

        # Support both local CA file and Vercel environment variable
        ca_content = os.getenv("DB_SSL_CA_CONTENT")
        ca_path = Config.DB_SSL_CA

        if ca_content:
            certificate_path = Path("/tmp/aiven-ca.pem")

            if (
                not certificate_path.exists()
                or certificate_path.read_text(encoding="utf-8") != ca_content
            ):
                certificate_path.write_text(ca_content, encoding="utf-8")

            ca_path = str(certificate_path)

        if ca_path:
            connection_config.update({
                "ssl_ca": ca_path,
                "ssl_verify_cert": True,
                "ssl_verify_identity": True
            })

        connection = mysql.connector.connect(**connection_config)

        if connection.is_connected():
            return connection

    except (Error, OSError) as error:
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
