import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "faculty_timetable_db")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))

    # Optional SSL certificate path for cloud databases such as Aiven
    DB_SSL_CA = os.getenv("DB_SSL_CA") or None

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "faculty_timetable_secret_key"
    )