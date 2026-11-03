
from getpass import getpass
from werkzeug.security import generate_password_hash
from mysql.connector import Error
from database.db import get_connection

username = input("Enter Admin username: ").strip()
password = getpass("Enter Admin password: ")
confirm_password = getpass("Confirm Admin password: ")

if not username or not password:
    print("Username and password cannot be empty.")
    raise SystemExit

if password != confirm_password:
    print("Passwords do not match.")
    raise SystemExit

connection = get_connection()

if connection is None:
    print("Database connection failed.")
    raise SystemExit

cursor = connection.cursor()

try:
    cursor.execute(
        "SELECT user_id FROM users WHERE username = %s",
        (username,)
    )

    if cursor.fetchone():
        print("This username already exists.")
    else:
        password_hash = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, 'ADMIN')
            """,
            (username, password_hash)
        )

        connection.commit()
        print("Admin account created successfully!")

except Error as error:
    connection.rollback()
    print("Error creating Admin:", error)

finally:
    cursor.close()
    connection.close()
