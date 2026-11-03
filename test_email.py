
import os
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

try:
    print("1. Checking email settings...")

    username = os.environ["MAIL_USERNAME"]
    password = os.environ["MAIL_PASSWORD"]
    sender = os.environ["MAIL_FROM"]
    host = os.environ.get("MAIL_HOST", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", "587"))

    message = EmailMessage()
    message["Subject"] = "Faculty Timetable Generator - Email Test"
    message["From"] = sender
    message["To"] = username
    message.set_content("Your email configuration test was successful.")

    print("2. Connecting to Gmail...")

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()

        print("3. Starting secure TLS connection...")
        server.starttls(context=ssl.create_default_context())
        server.ehlo()

        print("4. Authenticating with Gmail...")
        server.login(username, password)

        print("5. Sending test email...")
        server.send_message(message)

    print("SUCCESS: Test email sent. Check your inbox and spam folder.")

except Exception as error:
    print("FAILED AT OR AFTER THE LAST PRINTED STEP")
    print("Error type:", type(error).__name__)
    print("Error details:", str(error))
