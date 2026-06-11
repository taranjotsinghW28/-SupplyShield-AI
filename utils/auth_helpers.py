import re
import os
try:
    import resend
    _HAS_RESEND = True
except Exception:
    resend = None
    _HAS_RESEND = False
from flask_login import UserMixin
import bcrypt
from db_config import get_db_connection

BCRYPT_LOG_ROUNDS = int(os.getenv('BCRYPT_LOG_ROUNDS', 12))

# Initialize Resend
if _HAS_RESEND:
    resend.api_key = os.getenv("RESEND_API_KEY")

# ==========================================
# USER SESSION MODEL MIXIN FOR FLASK-LOGIN
# ==========================================
class UserSession(UserMixin):
    """Session container tracking logged-in managers."""
    def __init__(self, user_doc):
        self.id = str(user_doc["_id"])
        self.username = user_doc["username"]
        self.email = user_doc["email"]
        self.role = user_doc.get("role", "Manager")
        self.tier = user_doc.get("tier", "Free")

# ==========================================
# 1. CRYPTOGRAPHIC ENCRYPTION ENGINES
# ==========================================
def hash_password(password):
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')
    else:
        password_bytes = bytes(password)

    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]

    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')

    if len(plain_password) > 72:
        plain_password = plain_password[:72]

    return bcrypt.checkpw(plain_password, hashed_password)

# ==========================================
# 2. EMAIL VERIFICATION CHANNELS (Using Resend API)
# ==========================================
def validate_email_regex(email: str) -> bool:
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(email_regex, email))

def send_verification_email(user_email, token):
    """Sends verification email using Resend API."""
    verify_url = f"http://127.0.0.1:5000/verify/{token}"
    
    params = {
        "from": "onboarding@resend.dev",
        "to": user_email,
        "subject": "Verify your SupplyShield-AI Account",
        "html": f"<p>Welcome! Click the link below to verify your account:</p><a href='{verify_url}'>Verify Email</a>"
    }
    
    try:
        if _HAS_RESEND:
            return resend.Emails.send(params)
        else:
            # Local fallback: print email content to console for development
            print(f"[DEV EMAIL] To: {user_email} | Subject: {params['subject']} | Body: {params['html']}")
            return None
    except Exception as e:
        print(f"Resend API Error: {e}")
        return None

# ==========================================
# 3. TIER UPGRADE SYSTEM LOGIC
# ==========================================
def has_premium_access(user_doc) -> bool:
    if not user_doc:
        return False
    if user_doc.get("role") == "Admin":
        return True
    return user_doc.get("tier") == "Premium"


def ensure_subscription_active(username: str) -> bool:
    db = get_db_connection()
    existing = db.users.find_one({"username": username})
    if not existing:
        return False
    return has_premium_access(existing)


def upgrade_user_tier(username: str) -> bool:
    try:
        db = get_db_connection()
        existing = db.users.find_one({"username": username})
        if not existing:
            return False
        result = db.users.update_one(
            {"username": username},
            {"$set": {"tier": "Premium"}}
        )
        return result.modified_count > 0 or existing is not None
    except Exception:
        return False