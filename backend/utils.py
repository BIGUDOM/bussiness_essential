from functools import wraps
from flask import session, redirect
import traceback
import mysql.connector
from flask import (
     jsonify
)
from typing import Optional
import os
import requests
import base64
from dotenv import load_dotenv

load_dotenv()



CONFIG_FILE = "config.json"

conn = mysql.connector.connect(
        host = os.getenv("DB_HOST"),
        user =  os.getenv("DB_USER"),
        password =  os.getenv("DB_PASSWORD"),
        database =  os.getenv("DB_NAME"), 
        port =  os.getenv("DB_PORT"),
)
cursor = conn.cursor()

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return view(*args, **kwargs)
    return wrapped_view


def send_email(
    recipient: str,
    subject: str,
    body: str,
    html: bool = False,
    attachments: Optional[list] = None
) -> bool:
    try:
        api_key = os.getenv("RESEND_API_KEY")
        sender = os.getenv("SENDER_EMAIL")

        if not api_key or not sender:
            print("⚠️ Email not configured")
            return False

        files = []
        if attachments:
            for path in attachments:
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        files.append({
                            "filename": os.path.basename(path),
                            "content": base64.b64encode(f.read()).decode()
                        })
                else:
                    print(f"Attachment not found: {path}")

        payload = {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "html": body if html else None,
            "text": body if not html else None,
            "attachments": files if files else None
        }

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )

        if response.status_code >= 400:
            print("⚠️ Email error:", response.text)
            return False

        return True

    except Exception as e:
        print("⚠️ Email failed:", e)
        traceback.print_exc()
        return False


import threading

def send_email_async(recipient: str, subject: str, body: str, html: bool=False, attachments: Optional[list]=None):
    """Send email in a separate thread to avoid blocking requests."""
    def _send():
        try:
            success = send_email(recipient, subject, body, html, attachments)
            if not success:
                print(f"Failed to send email to {recipient}")
        except Exception as e:
            print(f"EMAIL THREAD ERROR: {e}")

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()

    
def get_user_id(username):
    cursor.execute("SELECT user_id, username FROM user_base WHERE username=%s", (username,))
    user = cursor.fetchone()

    if not user:
        return jsonify({
            "status": "error",
            "message": "User not found"
        }), 400
    
    
    user_id = user[0]

    return user_id