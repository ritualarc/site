import os
import smtplib
from email.message import EmailMessage

CONTACT_RECIPIENT = os.environ.get("CONTACT_RECIPIENT", "theritualarc@gmail.com")


class EmailNotConfiguredError(RuntimeError):
    pass


def send_contact_email(first_name: str, last_name: str, email: str, message: str) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_username or not smtp_password:
        raise EmailNotConfiguredError(
            "SMTP_USERNAME and SMTP_PASSWORD must be set to send contact emails."
        )

    msg = EmailMessage()
    msg["Subject"] = f"Website Contact: {first_name} {last_name}"
    msg["From"] = smtp_username
    msg["To"] = CONTACT_RECIPIENT
    msg["Reply-To"] = email
    msg.set_content(
        "\n".join(
            [
                f"First Name: {first_name}",
                f"Last Name: {last_name}",
                f"Email: {email}",
                "Message:",
                message,
            ]
        )
    )

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
