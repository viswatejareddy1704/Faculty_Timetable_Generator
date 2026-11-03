from database.db import get_connection


connection = get_connection()

if connection:
    print("✅ MySQL connection successful!")
    connection.close()
else:
    print("❌ MySQL connection failed.")