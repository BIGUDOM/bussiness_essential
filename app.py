from flask import (
    Flask, request, jsonify, session,redirect, Blueprint
)
from flask_cors import CORS
import hashlib
from datetime import datetime,timedelta
import secrets
import requests
import mysql.connector
import os
from backend.utils import login_required,get_user_id,send_email


conn = mysql.connector.connect(
        host = os.getenv("DB_HOST"),
        user =  os.getenv("DB_USER"),
        password =  os.getenv("DB_PASSWORD"),
        database =  os.getenv("DB_NAME"), 
        port =  os.getenv("DB_PORT"),
)
cursor = conn.cursor()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=True
)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

# ==========================
# CONSTANTS
# ==========================
APP_LOGO_URL = os.path.join('static', 'media', 'app logo.png')
SECURITY_URL = "https://yourapp.com/security-settings"
DASHBOARD_URL = "https://yourapp.com/dashboard"




@app.route("/api/cust", methods=["POST"])
def create_profile():
    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error",
            "message": "Invalid or missing JSON"
        }), 400

    required_fields = [
        "username",
        "profile_name",
        "full_name",
        "address",
        "country",
        "currency",
        "dob",
    ]

    # GET USER ID FOR INDEXING
    user_id = get_user_id(data['username'])
    if not user_id:
        return jsonify({
        "status": "error",
        "message": "User not found"
        }), 404

    # lOAD DATA FROM DATABASE TO ENSURE NO DUPLICATES
    cursor.execute("SELECT profilename FROM cust_base")
    existing_profiles = {row[0] for row in cursor.fetchall()}
    if data["profile_name"] in existing_profiles:
        return jsonify({
            "status": "error",
            "message": "Profile name already exists"
        }), 400
    
    # Validate required fields
    for field in required_fields:
        if not data.get(field):
            return jsonify({
                "status": "error",
                "message": f"Missing field: {field}"
            }), 400
    values = [    
            user_id,
            data["profile_name"],
            data["full_name"],
            data["address"],
            data["country"],
            data["currency"],
            data["dob"]
    ]
    for v in values:
        print(v)

    try:
        cursor.execute("""
            INSERT INTO cust_base
            (user_id,profilename, fullname, address, country, currency, dob)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            data["profile_name"],
            data["full_name"],
            data["address"],
            data["country"],
            data["currency"],
            data["dob"]
            
        ))

        conn.commit()

        return jsonify({
            "status": "success",
            "message": "Profile created successfully"
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({
            "status": "error",
            "message": "Database error",
            "details": str(e)
        }), 500


@app.route("/api/user", methods=["POST"])
def create_user():
    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error",
            "message": "Invalid or missing JSON"
        }), 400

    required_fields = [
        "username",
        "email",
        "password",
        "security_question",
        "security_answer"
    ]

    # Validate required fields FIRST
    for field in required_fields:
        if not data.get(field):
            return jsonify({
                "status": "error",
                "message": f"Missing field: {field}"
            }), 400

    try:
        # Check duplicate username properly
        cursor.execute(
            "SELECT 1 FROM user_base WHERE username = %s",
            (data["username"],)
        )
        if cursor.fetchone():
            return jsonify({
                "status": "error",
                "message": "Username already exists"
            }), 400

        # Insert user
        cursor.execute("""
            INSERT INTO user_base
            (username, email, password_hash, sequrity_question, sequrity_answer_hash,
             failed_attempts, last_login, last_failed_login, trial_ends_at,
             locked, lock_reason, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data["username"],
            data["email"],
            hashlib.sha256(data["password"].encode()).hexdigest(),
            data["security_question"],
            hashlib.sha256(data["security_answer"].encode()).hexdigest(),
            0,
            None,
            None,
            (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
            False,
            "",
            True
        ))

        conn.commit()

        code = secrets.token_hex(3)
        session['email_code'] = code
        send_email(
            data['email'],
            "Business Essential - Verify Your Email",
            f'Your verification code is {code}',
            html=False
        )

        return jsonify({
            "status": "success",
            "message": "User created successfully"
        }), 201

    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({
            "status": "error",
            "message": f"Database error {e}"
        }), 500

@app.route("/api/verify", methods=["POST"])
def verify_user():
    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error",
            "message": "Invalid or missing JSON"
        }), 400

    required_fields = [
       "entered_code"
    ]

    # Validate required fields
    for field in required_fields:
        if not data.get(field):
            return jsonify({
                "status": "error",
                "message": f"Missing field: {field}"
            }), 400

    genereted_code = session.get("email_code")
    # Here you would normally check the verification code against what was sent/stored
    if genereted_code != data["entered_code"]:
        return jsonify({
            "status": "error",
            "message": "Invalid verification code"
        }), 400
    
    session.clear()
    return jsonify({
        "status": "success",
        "message": "User verified successfully"
    }), 200



UPLOAD_FOLDER = "static/uploads"  # Make sure this folder exists
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/api/completecust", methods=["POST"])
def complete_cust():
    # Since we are sending FormData, use request.form and request.files
    form = request.form
    file = request.files.get("profile_picture")

    # Required fields
    required_fields = [
        "username",
        "email",
        "profile_name",
        "phone_number",
        "alternate_email",
        "website",
        "bio"
    ]

    # Validate required fields
    for field in required_fields:
        if not form.get(field):
            return jsonify({
                "status": "error",
                "message": f"Missing field: {field}"
            }), 400

    username = form.get("username")
    user_id = get_user_id(username)  # Assuming this function exists

    import os
    from werkzeug.utils import secure_filename

    UPLOAD_FOLDER = "static/uploads"

    # Ensure the upload folder exists
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)  # <-- creates the folder if missing

    # Example saving file
    file = request.files.get("profile_picture")  # Make sure your input type="file"
    if file:
        filename = secure_filename(f"{user_id}_{file.filename}")  # safe filename
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)



    try:
        cursor.execute("""
            UPDATE cust_base
            SET phone=%s,
                alternateemail=%s,
                website=%s,
                profilepicurl=%s,
                bio=%s
            WHERE profilename=%s AND user_id=%s
        """, (
            form.get("phone_number"),
            form.get("alternate_email"),
            form.get("website"),
            save_path,
            form.get("bio"),
            form.get("profile_name"),
            user_id
        ))

        cursor.execute(
            """
            INSERT INTO user_settings (user_id, footer_note
            )
            VALUES (%s, %s)
            """,
            (
                user_id,
                "Thanks for doing business with us."
            )
        )

        cursor.execute(
            """
            INSERT INTO wallet_base (user_id, date_created)
            VALUES(%s,%s)
            """,
            (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )

        conn.commit()

        # welcome html
        first_name = form['profile_name']
        year = datetime.now().year
        welcome_html = f"""

<body style="margin:0; padding:0; background-color:#f4f6f8; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr>
      <td align="center">


    <!-- Card -->
    <table width="100%" cellpadding="0" cellspacing="0"
      style="max-width:600px; background:#ffffff; border-radius:14px; box-shadow:0 10px 30px rgba(0,0,0,0.08); overflow:hidden;">

      <!-- Header -->
      <tr>
        <td style="background:linear-gradient(135deg, #2563eb, #1e40af); padding:28px; text-align:center;">
          <img src="{APP_LOGO_URL}" alt="Business Essential Logo" width="56" height="56"
            style="display:block; margin:0 auto 10px;" />
          <h1 style="margin:0; font-size:22px; color:#ffffff;">Welcome to Business Essential 🎉</h1>
          <p style="margin:6px 0 0; font-size:14px; color:#dbeafe;">
            Simple • Secure • Professional Invoicing
          </p>
        </td>
      </tr>

      <!-- Body -->
      <tr>
        <td style="padding:36px; color:#111827;">
          <h2 style="margin-top:0; font-size:24px;">
            Hi {first_name},
          </h2>

          <p style="font-size:15px; line-height:1.7;">
            Welcome aboard! We’re excited to have you join <strong>Business Essential</strong>.
            Your account has been successfully created, and you’re now ready to start managing
            invoices, customers, and payments with ease.
          </p>

          <!-- Feature List -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
            <tr>
              <td style="font-size:15px; line-height:1.8;">
                ✅ Create and manage professional invoices<br />
                ✅ Track payments and customer activity<br />
                ✅ Secure your account with built-in protections<br />
                ✅ Access your data anytime, anywhere
              </td>
            </tr>
          </table>

          <!-- CTA -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:32px 0;">
            <tr>
              <td align="center">
                <a href="{DASHBOARD_URL}"
                  style="background:#2563eb; color:#ffffff; text-decoration:none;
                         padding:14px 26px; border-radius:10px;
                         font-size:15px; font-weight:600; display:inline-block;">
                  Go to Dashboard
                </a>
              </td>
            </tr>
          </table>

          <p style="font-size:15px; line-height:1.7;">
            If you ever need help, our support team is always here to assist you.
            We recommend starting by completing your profile and creating your first invoice.
          </p>

          <p style="font-size:15px; line-height:1.7;">
            We’re glad you’re here — let’s build something great together 🚀
          </p>

          <p style="margin-top:32px; font-size:14px; color:#374151;">
            Warm regards,<br />
            <strong>The Business Essential Team</strong>
          </p>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#f9fafb; padding:18px; text-align:center; font-size:12px; color:#6b7280;">
          You’re receiving this email because you created an Business Essential account.<br />
          © {year} Business Essential. All rights reserved.
        </td>
      </tr>

    </table>

  </td>
</tr>


  </table>

</body>

"""
        send_email(
            recipient=form["email"],
            subject="Welcome to Business Essential 🎉",
            body=welcome_html,
            html=True
        )

        return jsonify({
            "status": "success",
            "message": "Customer profile completed successfully"
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({
            "status": "error",
            "message": "Database error",
            "details": str(e)
        }), 500




    
@app.route("/api/resend", methods=["POST"])
def resend_verification():
    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error",
            "message": "Invalid or missing JSON"
        }), 400

    required_fields = [
        "email",
        "verification_code"
    ]

    for field in required_fields:
        if not data.get(field):
            return jsonify({
                "status": "error",
                "message": f"Missing field: {field}"
            }), 400

    send_email(
        recipient=data["email"],
        subject="Verification Code Resent",
        body=f"Here is your verification code: {data['verification_code']}",
        html=False
    )

    return jsonify({
        "status": "success",
        "message": "Verification code resent successfully"
    }), 200

@app.route("/loginp", methods=["POST"])
def verifylogin():
    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error",
            "message": "Invalid or missing JSON"
        }), 400
    
    required_fields = [
        'username',
        'password'
    ]

    # Validate required fields
    for field in required_fields:
        if not data.get(field):
            return jsonify({
                "status": "error",
                "message": f"Missing field: {field}"
            }), 400
        
    try:
        cursor.execute(
            """
            SELECT password_hash, locked, failed_attempts, last_failed_login,email,lock_reason, user_id
            FROM user_base
            WHERE username=%s
            """,
            (data['username'],)
        )
        user = cursor.fetchone()

        if not user:
            return jsonify({
                "status": "error",
                "message":"User not found"
            }),400
        
        if user[1]:
            return jsonify({
                "status": "error",
                "message":  f"Account locked! Reason: {user[5]}" 
            }), 400
        


        current_password = user[0]
        password = data['password']
        hashed = hashlib.sha256(password.encode()).hexdigest()
        user_id = user[6]

        if hashed != current_password:
            # Failed attempt
            new_attempts = user[2] + 1  
            cursor.execute(
                "UPDATE user_base SET failed_attempts=%s, last_failed_login=NOW() WHERE username=%s",
                (new_attempts, data['username']),
            )
            conn.commit()

            if new_attempts >= 3:
                cursor.execute(
                    "UPDATE user_base SET locked=1, lock_reason=%s WHERE username=%s",
                    ("Too many failed login attempts", data['username']),
                )
                conn.commit()
            return jsonify({
                "status": "error",
                "message": "Incorrect Password"
            }), 400
        

        # --- Successful login ---

        cursor.execute(
            "UPDATE user_base SET failed_attempts=0, last_login= NOW() WHERE username=%s",
            (data['username'],)
        )


        cursor.execute(
            """
            SELECT *
            FROM wallet_base
            WHERE user_id=%s
            """,
            (user_id,)
        )
        w = cursor.fetchone()
        if not w :
            cursor.execute(
                """
                INSERT INTO wallet_base (user_id, date_created)
                VALUES(%s,%s)
                """,
                (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )

        cursor.execute(
            """
            SELECT trial_ends_at 
            FROM user_base 
            WHERE user_id=%s
            """,
            (user_id,)
        )
        trial = cursor.fetchone()
        if trial and trial[0] is None:
            cursor.execute(
                """
                UPDATE user_base
                SET trial_ends_at=%s
                WHERE user_id=%s
                """,
                ((datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"), user_id)
            )
        

        conn.commit()

  
    
        # --- Send login notification ---
        email = str(user[4]) if user[4] else None # type: ignore
        # Build login HTML

        def get_location_from_ip(ip):
            try:
                response = requests.get(f"https://ipinfo.io/{ip}/json", timeout=5)
                data = response.json()

                city = data.get("city", "Unknown City")
                region = data.get("region", "Unknown Region")
                country = data.get("country", "Unknown Country")
                return city, region, country
            except Exception:
                return "Unknown City", "Unknown Region", "Unknown Country"

        def get_client_ip(request):
            if request.headers.get("X-Forwarded-For"):
                return request.headers.get("X-Forwarded-For").split(",")[0]
            return request.remote_addr

        login_ip = get_client_ip(request)
        city, region, country = get_location_from_ip(login_ip)
        year = datetime.now().year

        login_html = f"""

<body style="margin:0; padding:0; background-color:#f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr>
      <td align="center">


    <!-- Main Card -->
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px; background:#ffffff; border-radius:12px; box-shadow:0 8px 24px rgba(0,0,0,0.08); overflow:hidden;">

      <!-- Header -->
      <tr>
        <td style="background:#111827; padding:24px; text-align:center;">
          <img src="{APP_LOGO_URL}" alt="Business Essential Logo" width="48" height="48" style="display:block; margin:0 auto 8px;" />
          <h1 style="color:#ffffff; font-size:20px; margin:0;">Business Essential</h1>
          <p style="color:#9ca3af; margin:4px 0 0; font-size:14px;">Security Notification</p>
        </td>
      </tr>

      <!-- Content -->
      <tr>
        <td style="padding:32px; color:#111827;">
          <h2 style="margin-top:0; font-size:22px;">New Sign-In Detected</h2>

          <p style="font-size:15px; line-height:1.6;">
            We noticed a new sign-in to your Invoice App account.  
            For your security, we’re letting you know whenever your account is accessed from a new device or location.
          </p>

          <!-- Details Box -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0; background:#f9fafb; border-radius:8px; padding:16px;">
            <tr>
              <td style="font-size:14px; line-height:1.8;">
                <strong>Login details</strong><br />
                <strong>IP Address:</strong> {login_ip}<br />
                <strong>Location:</strong> {city}, {region}, {country}<br />
                <strong>Date & Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br />
                <strong>Device:</strong> New or unrecognized device
              </td>
            </tr>
          </table>

          <p style="font-size:15px; line-height:1.6;">
            <strong>Was this you?</strong><br />
            If you recognize this activity, no action is required. You can safely ignore this message.
          </p>

          <p style="font-size:15px; line-height:1.6;">
            <strong>Was this not you?</strong><br />
            If you do not recognize this sign-in, we strongly recommend taking action immediately to protect your account:
          </p>

          <ul style="font-size:15px; line-height:1.6; padding-left:20px;">
            <li>Change your account password</li>
            <li>Review recent account activity</li>
            <li>Update your security questions or recovery details</li>
          </ul>

          <!-- CTA Button -->
          <table cellpadding="0" cellspacing="0" style="margin:28px 0;">
            <tr>
              <td align="center">
                <a href="{SECURITY_URL}" style="background:#2563eb; color:#ffffff; text-decoration:none; padding:12px 20px; border-radius:8px; font-weight:600; display:inline-block;">
                  Secure My Account
                </a>
              </td>
            </tr>
          </table>

          <p style="font-size:14px; color:#374151; line-height:1.6;">
            If you believe your account has been compromised or need assistance, please contact our support team immediately.
          </p>

          <p style="font-size:14px; color:#6b7280; margin-top:32px;">
            Thank you for helping us keep your account secure,<br />
            <strong>The Business Essential Security Team</strong>
          </p>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#f9fafb; padding:16px; text-align:center; font-size:12px; color:#6b7280;">
          This is an automated security message. Please do not reply.<br />
          © {year} Business Essential. All rights reserved.
        </td>
      </tr>

    </table>

  </td>
</tr>


  </table>

</body>


        """
        
        token = jwt.encode({
            "user_id": user_id,
            "exp": datetime.utcnow() + timedelta(days=7)
        }, app.config["SECRET_KEY"], algorithm="HS256")

        send_email(
            recipient=email,
            subject="New Sign-In Detected — Business Essential",
            body=login_html,
            html=True
        )


        session['user_id'] = user_id

        return jsonify({
            "status": "success",
            "message": "Login successful",
            "token": token
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({
            "status": "error",
            "message": "Database error",
            "details": str(e)
        }), 500


if __name__ == "__main__":
    app.run()





