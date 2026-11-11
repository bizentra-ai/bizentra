import smtplib
from email.message import EmailMessage
from fastapi import HTTPException
from . import config

def deliver(recipient, subject, body):
    if not config.EMAIL_HOST:
        if config.ENVIRONMENT == 'development':
            return False
        raise HTTPException(503, 'Email delivery has not been configured.')
    message = EmailMessage()
    message['Subject'], message['From'], message['To'] = subject, config.EMAIL_FROM, recipient
    message.set_content(body)
    try:
        with smtplib.SMTP(config.EMAIL_HOST, config.EMAIL_PORT, timeout=10) as client:
            client.starttls()
            if config.EMAIL_USERNAME:
                client.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
            client.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        raise HTTPException(503, 'Email delivery failed. Please try again later.')
