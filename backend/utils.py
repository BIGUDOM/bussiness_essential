from functools import wraps
from flask import session, redirect,request, jsonify
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
import jwt
import random
from user_agents import parse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from typing import Optional
from datetime import datetime,timedelta


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


SECRET_KEY = os.getenv("SECRET_KEY")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            token = auth_header.split(" ")[1]

        if not token:
            return jsonify({
                "status": "error",
                "message": "Token is missing"
            }), 401

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user_id = payload["user_id"]
            current_user_role = payload["role"]

        except jwt.ExpiredSignatureError:
            return jsonify({
                "status": "error",
                "message": "Token expired"
            }), 401

        except Exception:
            return jsonify({
                "status": "error",
                "message": "Invalid token"
            }), 401

        return f(current_user_id, current_user_role, *args, **kwargs)

    return decorated


LOGO_PATH = os.path.join('static', 'media', 'app logo.png')  # Replace with your logo path


def generate_invoice_pdf(invoice_id, client_name, client_email,
                         invoice_date, due_date, status,
                         items, subtotal, tax, total,
                         amount_paid, balance, notes):

    filename = f"invoice_{invoice_id}.pdf"
    file_path = os.path.join("C:\\Users\\Elitebook 1040 G6\\OneDrive\\Desktop\\web developmen\\reciept app\\static\\invoices", filename)
    os.makedirs("C:\\Users\\Elitebook 1040 G6\\OneDrive\\Desktop\\web developmen\\reciept app\\static\\invoices", exist_ok=True)


    doc = SimpleDocTemplate(file_path, pagesize=A4,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)

    styles = getSampleStyleSheet()
    elements = []

    brand_color = colors.HexColor("#1558B0")  # Brand primary color

    # ---------- App Logo ----------
    logo_path = LOGO_PATH
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=120, height=40)
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 12))

    # ---------- Invoice Header ----------
    status_color = colors.green if status.lower() == "paid" else colors.red
    elements.append(Paragraph(
        f"<b>Invoice #{invoice_id}</b>",
        ParagraphStyle(
            name="InvoiceTitle",
            fontSize=20,
            textColor=brand_color,
            alignment=0,  # left
            spaceAfter=8
        )
    ))
    elements.append(Paragraph(
        f"<b>Status:</b> <font color='#{status_color.hexval()}'>{status.upper()}</font>",
        ParagraphStyle(
            name="InvoiceStatus",
            fontSize=12,
            spaceAfter=15
        )
    ))

    # ---------- Client & Invoice Info ----------
    info_table = Table([
        ["Bill To:", client_name, "Invoice Date:", invoice_date],
        ["Email:", client_email, "Due Date:", due_date],
    ], colWidths=[70, 180, 90, 140])

    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("FONT", (0,0), (-1,-1), "Helvetica"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))

    # ---------- Items Table ----------
    item_data = [["Description", "Qty", "Price", "Total"]]
    for idx, item in enumerate(items):
        line_total = item["quantity"] * item["price"]
        item_data.append([
            item["description"],
            item["quantity"],
            f"₦{item['price']:,.2f}",
            f"₦{line_total:,.2f}"
        ])

    items_table = Table(item_data, colWidths=[250, 60, 90, 90])
    # Alternating row colors for readability
    row_colors = [colors.HexColor("#f9f9f9") if i % 2 == 0 else colors.white for i in range(len(item_data))]
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), brand_color),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("BOTTOMPADDING", (0,0), (-1,0), 10),
        ("TOPPADDING", (0,0), (-1,0), 10),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    for i, color in enumerate(row_colors):
        if i == 0:  # skip header
            continue
        items_table.setStyle(TableStyle([("BACKGROUND", (0,i), (-1,i), color)]))

    elements.append(items_table)
    elements.append(Spacer(1, 20))

    # ---------- Totals Table ----------
    totals_data = [
        ["Subtotal:", f"₦{subtotal:,.2f}"],
        ["Tax:", f"₦{tax:,.2f}"],
        ["Total:", f"₦{total:,.2f}"],
        ["Amount Paid:", f"₦{amount_paid:,.2f}"],
        ["Balance:", f"₦{balance:,.2f}"]
    ]
    totals_table = Table(totals_data, colWidths=[350, 140], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
        ("FONT", (0,0), (-1,-1), "Helvetica-Bold"),
        ("LINEBEFORE", (1,0), (1,-1), 0.5, colors.grey),
        ("LINEABOVE", (0,-1), (-1,-1), 1, colors.black),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TEXTCOLOR", (1,4), (1,4), colors.red if balance > 0 else colors.green)  # Balance
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 20))

    # ---------- Notes ----------
    if notes:
        elements.append(Paragraph(f"<b>Notes:</b><br/>{notes}", styles["Normal"]))

    # ---------- Build PDF ----------
    doc.build(elements)
    return file_path

def send_basic_plan_invoice_email(
    client_email, client_name, invoice_id,
    invoice_date, due_date, status,
    subtotal, tax, total, amount_paid,
    balance, notes, items
):
  

    # Generate PDF
    pdf_path = generate_invoice_pdf(
        invoice_id, client_name, client_email,
        invoice_date, due_date, status,
        items, subtotal, tax, total,
        amount_paid, balance, notes
    )

    app_logo = os.path.join("static", "media", "app logo.png")

    html_body = f"""
    <div style="font-family:Arial, sans-serif; max-width:650px; margin:auto; border:1px solid #e0e0e0; padding:20px; background:#fdfdfd;">
        <div style="text-align:center; margin-bottom:20px;">
            <img src='{app_logo}' alt='Business Essential' style='height:50px;'/>
            <h2 style="color:#1558B0; margin:5px 0;">Invoice #{invoice_id}</h2>
        </div>

        <p>Hello <b>{client_name}</b>,</p>
        <p>Here is your invoice summary:</p>

        <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse; margin-bottom:15px;">
            <tr><td style="font-weight:bold;">Invoice Date:</td><td>{invoice_date}</td></tr>
            <tr><td style="font-weight:bold;">Due Date:</td><td>{due_date}</td></tr>
            <tr><td style="font-weight:bold;">Status:</td><td><b>{status.upper()}</b></td></tr>
            <tr><td style="font-weight:bold;">Total:</td><td><b>₦{total:,.2f}</b></td></tr>
            <tr><td style="font-weight:bold;">Amount Paid:</td><td>₦{amount_paid:,.2f}</td></tr>
            <tr><td style="font-weight:bold;">Balance:</td><td><b>₦{balance:,.2f}</b></td></tr>
        </table>

        <p>Invoice items:</p>
        <table width="100%" cellpadding="6" cellspacing="0" style="border-collapse:collapse; border:1px solid #ddd; margin-bottom:15px;">
            <tr style="background:#1558B0; color:white;">
                <th align="left">Description</th>
                <th align="center">Qty</th>
                <th align="right">Price</th>
                <th align="right">Total</th>
            </tr>
            {''.join(f"<tr><td>{i['description']}</td><td align='center'>{i['quantity']}</td><td align='right'>₦{i['price']:,.2f}</td><td align='right'>₦{i['quantity']*i['price']:,.2f}</td></tr>" for i in items)}
        </table>

        <p style="margin-top:10px;">
            <b>Subtotal:</b> ₦{subtotal:,.2f}<br/>
            <b>Tax:</b> ₦{tax:,.2f}<br/>
            <b>Total:</b> ₦{total:,.2f}<br/>
            <b>Amount Paid:</b> ₦{amount_paid:,.2f}<br/>
            <b>Balance:</b> ₦{balance:,.2f}
        </p>

        {f"<p><b>Notes:</b> {notes}</p>" if notes else ""}
        <p>Thank you for doing business with us.<br/><b>Business Essential</b></p>
    </div>
    """

    send_email(
        recipient=client_email,
        subject=f"Business Essential - Invoice #{invoice_id}",
        body=html_body,
        html=True,
        attachments=[pdf_path]
    )


def send_pro_plan_invoice_email(
    client_email, client_name, invoice_id,
    invoice_date, due_date, status,
    subtotal, tax, total, amount_paid,
    balance, notes, items
):
    from pathlib import Path

    pay_link = f"https://yourapp.com/pay/invoice/{invoice_id}"

    # Generate PDF
    pdf_path = generate_invoice_pdf(
        invoice_id, client_name, client_email,
        invoice_date, due_date, status,
        items, subtotal, tax, total,
        amount_paid, balance, notes
    )
    app_logo = os.path.join("static", "media", "app logo.png")

    html_body = f"""
    <div style="font-family:'Segoe UI', Arial, sans-serif; max-width:700px; margin:auto; border:1px solid #e0e0e0; padding:25px; background:#fff;">
        <div style="text-align:center; margin-bottom:25px;">
            <img src='{app_logo}' alt='Business Essential' style='height:60px;'/>
            <h1 style="color:#1558B0; margin:5px 0;">Invoice #{invoice_id}</h1>
        </div>

        <p>Hello <b>{client_name}</b>,</p>
        <p>Here are your invoice details:</p>

        <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse; margin-bottom:20px;">
            <tr><td style="font-weight:bold;">Invoice Date:</td><td>{invoice_date}</td></tr>
            <tr><td style="font-weight:bold;">Due Date:</td><td>{due_date}</td></tr>
            <tr><td style="font-weight:bold;">Status:</td><td><b>{status.upper()}</b></td></tr>
            <tr><td style="font-weight:bold;">Total:</td><td><b>₦{total:,.2f}</b></td></tr>
            <tr><td style="font-weight:bold;">Amount Paid:</td><td>₦{amount_paid:,.2f}</td></tr>
            <tr><td style="font-weight:bold;">Balance:</td><td><b>₦{balance:,.2f}</b></td></tr>
        </table>

        <p>Invoice Items:</p>
        <table width="100%" cellpadding="6" cellspacing="0" style="border-collapse:collapse; border:1px solid #ddd; margin-bottom:20px;">
            <tr style="background:#1558B0; color:white;">
                <th align="left">Description</th>
                <th align="center">Qty</th>
                <th align="right">Price</th>
                <th align="right">Total</th>
            </tr>
            {''.join(f"<tr><td>{i['description']}</td><td align='center'>{i['quantity']}</td><td align='right'>₦{i['price']:,.2f}</td><td align='right'>₦{i['quantity']*i['price']:,.2f}</td></tr>" for i in items)}
        </table>

        <div style="margin-bottom:20px;">
            <p><b>Subtotal:</b> ₦{subtotal:,.2f} | <b>Tax:</b> ₦{tax:,.2f} | <b>Total:</b> ₦{total:,.2f}</p>
            <p><b>Amount Paid:</b> ₦{amount_paid:,.2f} | <b>Balance:</b> ₦{balance:,.2f}</p>
        </div>

        {f"<p><b>Notes:</b> {notes}</p>" if notes else ""}

        <div style="text-align:center; margin:30px 0;">
            <a href="{pay_link}" style="background:#28a745; color:white; padding:12px 25px; text-decoration:none; border-radius:5px; font-weight:bold;">
                Pay Now
            </a>
        </div>

        <p style="text-align:center; color:#555;">Thank you for choosing <b>Business Essential</b></p>
    </div>
    """

    send_email(
        recipient=client_email,
        subject=f"Business Essential - Invoice #{invoice_id}",
        body=html_body,
        html=True,
        attachments=[pdf_path]
    )



def send_invoice_email(email, name, invoice_id, amount, due_date):
    pay_link = f"https://yourapp.com/pay/invoice/{invoice_id}"

    subject = f"Bussiness Essential - Invoice #{invoice_id} – Payment Request"


    # --------- HTML email ----------
    html_body = f"""
    <body style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, Helvetica, sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:30px 15px;">
            <table width="100%" max-width="600px" style="background:#ffffff; border-radius:10px; overflow:hidden; box-shadow:0 8px 30px rgba(0,0,0,0.08);">

              <!-- Header -->
              <tr>
                <td style="background:#4f46e5; padding:24px; text-align:center;">
                  <h1 style="margin:0; color:#ffffff; font-size:22px;">
                    Business Essential
                  </h1>
                  <p style="margin:6px 0 0; color:#e0e7ff; font-size:14px;">
                    Invoice Payment Request
                  </p>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:28px;">
                  <p style="font-size:15px; color:#111827;">
                    Hi <strong>{name}</strong>,
                  </p>

                  <p style="font-size:14px; color:#374151; line-height:1.6;">
                    You have received a new invoice from <strong>Business Essential</strong>.
                    Please review the details below and make payment before the due date.
                  </p>

                  <!-- Invoice Summary -->
                  <table width="100%" style="margin:20px 0; border-collapse:collapse;">
                    <tr>
                      <td style="padding:10px; border:1px solid #e5e7eb; background:#f9fafb;">
                        Invoice Number
                      </td>
                      <td style="padding:10px; border:1px solid #e5e7eb;">
                        #{invoice_id}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:10px; border:1px solid #e5e7eb; background:#f9fafb;">
                        Amount Due
                      </td>
                      <td style="padding:10px; border:1px solid #e5e7eb; font-weight:bold;">
                        ₦{amount}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:10px; border:1px solid #e5e7eb; background:#f9fafb;">
                        Due Date
                      </td>
                      <td style="padding:10px; border:1px solid #e5e7eb;">
                        {due_date}
                      </td>
                    </tr>
                  </table>

                  <!-- CTA Button -->
                  <div style="text-align:center; margin:30px 0;">
                    <a href="{pay_link}"
                       style="background:#4f46e5; color:#ffffff; text-decoration:none;
                              padding:14px 26px; border-radius:8px; font-size:15px;
                              display:inline-block;">
                      Pay Invoice Securely
                    </a>
                  </div>

                  <p style="font-size:13px; color:#6b7280; line-height:1.6;">
                    If you have already made this payment, please ignore this message.
                    For any questions, simply reply to this email.
                  </p>

                  <p style="font-size:13px; color:#6b7280;">
                    Thank you for your business,<br>
                    <strong>Business Essential</strong>
                  </p>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="background:#f9fafb; padding:18px; text-align:center;">
                  <p style="margin:0; font-size:12px; color:#9ca3af;">
                    © {datetime.now().year} Business Essential · Secure Invoicing Platform
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    """

    send_email(
        recipient=email,
        subject=subject,
        body=html_body,
        html= True,
  
    )

def generate_reference(invoice_prefix):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = random.randint(1000,9999)
    return f"{invoice_prefix}-{timestamp}-{rand}"


def save_log_activity(user_id, type_, title, description, amount: Optional[float] = None, status: Optional[str] = None):
    cursor.execute(
        "INSERT INTO log_activity (user_id, type, title, description) VALUES (%s,%s,%s,%s)",
        (user_id, type_, title, description)
    )
    if amount and status:
        cursor.execute(
            "INSERT INTO log_activity (user_id, type, title, description,amount,status) VALUES (%s,%s,%s,%s,%s,%s)",
            (user_id, type_, title, description,amount,status)
        )   

    conn.commit()

def parse_user_agent(user_agent_string):
    ua = parse(user_agent_string)

    # ---------- DEVICE NAME ----------
    if ua.is_mobile:
        device_family = ua.device.family

        # Apple devices improvement
        if device_family in ["iPhone", "iPad"]:
            device_model = device_family
        elif device_family == "Generic Smartphone":
            device_model = "Android Phone"
        else:
            device_model = device_family

    elif ua.is_tablet:
        device_model = ua.device.family or "Tablet"

    elif ua.is_pc:
        if "Windows" in ua.os.family:
            device_model = "Windows PC"
        elif "Mac" in ua.os.family:
            device_model = "Mac"
        elif "Linux" in ua.os.family:
            device_model = "Linux PC"
        else:
            device_model = "PC"

    else:
        device_model = ua.device.family or "Unknown Device"

    # ---------- CLIENT ----------
    client_type = ua.browser.family or "Unknown Browser"

    # ---------- OS ----------
    os_name = ua.os.family or "Unknown OS"
    os_version = ua.os.version_string or ""


    return device_model, client_type, os_name, os_version

def detect_location():
     ip = request.headers.get("X-Forwarded-For", request.remote_addr)
     response = requests.get(f"http://ipwho.is/{ip}")
     data = response.json()

     country = data.get("country")
     state = data.get("region")
     city = data.get("city")

     return country, state, city





