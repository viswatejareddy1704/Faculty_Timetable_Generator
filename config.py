import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "faculty_timetable_db")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "faculty_timetable_secret_key"
    )