#!/usr/bin/env python3
"""Send a CivicLens watchdog alert email.

Credentials come from ~/.watchdown_smtp.env style env file (sourced by the
caller) or existing environment — never from argv, so they stay out of
process listings. Usage: lockdown_notify.py "subject" "body"
"""
import os
import smtplib
import sys
from email.message import EmailMessage

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASS = os.environ["SMTP_PASS"]
NOTIFY_TO = os.environ.get("NOTIFY_TO", SMTP_USER)

subject = sys.argv[1] if len(sys.argv) > 1 else "CivicLens watchdog alert"
body = sys.argv[2] if len(sys.argv) > 2 else ""

msg = EmailMessage()
msg["From"] = SMTP_USER
msg["To"] = NOTIFY_TO
msg["Subject"] = subject
msg.set_content(body)

with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
    s.starttls()
    s.login(SMTP_USER, SMTP_PASS)
    s.send_message(msg)

print("NOTIFY_SENT")
