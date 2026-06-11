import os
import threading
from datetime import datetime, timedelta, timezone
from bson.objectid import ObjectId
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp
import secrets # Needed for token generation
import threading # Needed for background email sending
from db_config import get_db_connection, db
from models import create_user_model, create_supplier_model
from utils.auth_helpers import (
    UserSession, hash_password, verify_password, 
    validate_email_regex, send_verification_email, upgrade_user_tier,
    has_premium_access
)
import csv
import io
import math
import re
import pandas as pd
from utils.background_worker import run_analysis_in_background

# ReportLab libraries for PDF compilation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart

# ==========================================
# APPLICATION CONFIGURATION INITIALIZATION
# ==========================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_fallback_secret_key_10934')

# Establish connection handles to MongoDB Atlas (lazy — first request triggers connect)

# Initialize the Flask-Login Session Tracking Core
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_route'

@login_manager.user_loader
def load_user(user_id):
    """Retrieves an active database manager profile node when verifying sessions."""
    user_doc = db.users.find_one({"_id": ObjectId(user_id)})
    if user_doc:
        return UserSession(user_doc)
    return None


def get_user_doc(username):
    try:
        return db.users.find_one({"username": username})
    except Exception as exc:
        print(f"[WARN] Database unavailable while fetching user: {exc}")
        return None


def current_user_has_premium_access():
    user_doc = get_user_doc(current_user.username)
    return has_premium_access(user_doc)


admin_initialized = False

def create_default_admin_account():
    admin_username = "admin"
    admin_email = "admin@supplyshield.local"
    admin_password = "Admin@2026"
    existing_admin = get_user_doc(admin_username)
    if not existing_admin:
        admin_user = create_user_model(admin_username, admin_email, hash_password(admin_password), role="Admin", tier="Premium")
        db.users.insert_one(admin_user)
        print(f"[INIT] Default admin account created: {admin_username}")


@app.before_request
def initialize_admin():
    global admin_initialized
    if admin_initialized:
        return
    try:
        create_default_admin_account()
        admin_initialized = True
    except Exception as exc:
        print(f"[WARN] Could not initialize default admin account yet: {exc}")

# ==========================================
# SECURE FORM ARCHITECTURAL OBJECTS
# ==========================================
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=30)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, max=72)])
    submit = SubmitField('Enter Platform System')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=30)])
    email = StringField(
        'Email',
        validators=[
            DataRequired(),
            Regexp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', message='Enter a valid email address.')
        ]
    )
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, max=72)])
    tier = StringField('Tier', default='Free')
    submit = SubmitField('Register Terminal Account')


MAX_CSV_ROWS = 250
MAX_CSV_COLUMNS = 40
MAX_CSV_BYTES = 512_000


def _normalize_csv_header(name):
    return str(name).strip().lower()


def _serializable_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _parse_delivery_history(raw_value):
    if raw_value is None:
        return [100.0]
    if isinstance(raw_value, (list, tuple)):
        raw_values = raw_value
    else:
        raw_values = str(raw_value).strip()
        if raw_values == '':
            return [100.0]
        raw_values = raw_values.split(',')

    parsed = []
    for item in raw_values:
        if item is None:
            continue
        token = str(item).strip()
        if not token:
            continue
        try:
            parsed.append(float(token))
        except ValueError:
            continue
    return parsed or [100.0]


def _find_column_field(row, aliases):
    for alias in aliases:
        if alias in row:
            value = row[alias]
            if value is not None and str(value).strip() != "":
                return value
    return None


def _infer_supplier_name(row, row_number):
    name_aliases = [
        "name", "supplier_name", "vendor", "vendor_name", "company", "company_name",
        "supplierid", "vendor_id", "partner", "entity", "supplier name"
    ]
    supplier_name = _find_column_field(row, name_aliases)
    if supplier_name:
        return str(supplier_name).strip()

    for key, value in row.items():
        if value is None:
            continue
        candidate = str(value).strip()
        if candidate:
            # Try using the first text column value as a meaningful name
            try:
                float(candidate)
                continue  # skip if it's a number
            except ValueError:
                pass
            return f"Supplier-{row_number + 1}-{candidate[:20]}"
    return None


def _validate_csv_payload(df):
    if len(df) == 0:
        raise ValueError("CSV contained no rows. Provide at least one record to analyze.")
    if len(df) > MAX_CSV_ROWS:
        raise ValueError(
            f"Dataset too large for this analysis engine. Reduce your file to {MAX_CSV_ROWS} rows or fewer."
        )
    if len(df.columns) > MAX_CSV_COLUMNS:
        raise ValueError(
            f"CSV structure contains too many columns ({len(df.columns)}). Keep it under {MAX_CSV_COLUMNS} columns for reliable analysis."
        )
    raw_size = len(df.to_csv(index=False).encode('utf-8'))
    if raw_size > MAX_CSV_BYTES:
        raise ValueError(
            "Dataset too large for analysis processing. Please slim the file or split it into smaller manifest batches."
        )


def _load_supplier_row(row, row_number=0):
    aliases = {
        "name": ["name", "supplier_name", "supplierid", "vendor", "vendor_name", "company", "company_name", "partner", "entity", "supplier name"],
        "category": ["category", "sector", "classification", "vertical", "industry", "product type", "product_type"],
        "country": ["country", "region", "location", "nation", "origin", "locality"],
        "contact_email": ["contact_email", "email", "supplier_email", "contact", "vendor_email"],
        "certifications": ["certifications", "certs", "certification", "licenses", "standards", "inspection results", "inspection_results"],
        "delivery_history": ["delivery_history", "history", "performance_history", "on_time_history", "on_time_rate", "delivery_rate", "lead times", "lead_times", "shipping times", "shipping_times"]
    }

    supplier_name = _infer_supplier_name(row, row_number)
    if not supplier_name:
        raise ValueError(
            "CSV requires at least one identifiable supplier field. Add a name/vendor column or include a unique text field per row."
        )

    category = _find_column_field(row, aliases["category"]) or "Unknown"
    country = _find_column_field(row, aliases["country"]) or "Unknown"
    contact_email = _find_column_field(row, aliases["contact_email"]) or ""
    cert_raw = _find_column_field(row, aliases["certifications"]) or ""
    history_raw = _find_column_field(row, aliases["delivery_history"]) or "100"

    delivery_history = _parse_delivery_history(history_raw)
    certifications = [c.strip() for c in str(cert_raw).split(',') if c.strip()] if cert_raw else []
    raw_columns = {str(key): _serializable_value(value) for key, value in row.items()}

    return {
        "name": str(supplier_name).strip(),
        "category": str(category).strip(),
        "country": str(country).strip(),
        "contact_email": str(contact_email).strip(),
        "certifications": certifications,
        "delivery_history": delivery_history,
        "overall_on_time_rate": round(delivery_history[-1] if delivery_history else 100.0, 2),
        "hazard_score": 0.0,
        "risk_status": "Low",
        "ai_risk_summary": "",
        "smart_mitigation_steps": "",
        "historical_timeline": [],
        "last_checked": datetime.now(timezone.utc),
        "processing_status": "Pending",
        "raw_columns": raw_columns
    }

# ==========================================
# STEP 1: AUTHENTICATION ROUTE HANDLERS
# ==========================================
@app.route('/auth/register', methods=['GET', 'POST'])
def register_route():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_route'))
        
    form = RegisterForm()
    if form.validate_on_submit():
        username_input = form.username.data.strip()
        email_input = form.email.data.strip().lower()
        password_input = form.password.data
        tier_input = request.form.get('tier', 'Free')
        if tier_input not in ['Free', 'Premium']:
            tier_input = 'Free'
        
        # Keep your regex validation
        if not validate_email_regex(email_input):
            flash("Registration Rejected: Email formatting syntax pattern is invalid.")
            return render_template('auth/register.html', form=form)
        
        # Proceed to register
        secure_hash = hash_password(password_input)
        new_user = create_user_model(username_input, email_input, secure_hash, tier=tier_input)
        db.users.insert_one(new_user)
        
        # Generate token and send email
        token = secrets.token_urlsafe(32)
        db.users.update_one({"email": email_input}, {"$set": {"verification_token": token}})
        
        # Fire and forget the email via Resend
        threading.Thread(target=send_verification_email, args=(email_input, token)).start()
        
        flash("Account verification deployed smoothly! Check your email.")
        return redirect(url_for('login_route'))

    # If GET or validation failed without explicit return above, render the registration form
    return render_template('auth/register.html', form=form)



# ==========================================
# VERIFICATION ROUTE (Add this to your app.py)
# ==========================================
@app.route('/verify/<token>')
def verify_email(token):
    # Find the user by the verification token
    user = db.users.find_one({"verification_token": token})
    
    if user:
        # Mark email_verified as True and remove the token so it can't be used again
        db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"email_verified": True}, "$unset": {"verification_token": ""}}
        )
        flash("Email verified successfully! You can now log in.")
        return redirect(url_for('login_route'))
    
    # If the token is invalid or already used
    flash("Invalid or expired verification link.")
    return redirect(url_for('register_route'))

@app.route('/auth/login', methods=['GET', 'POST'])
def login_route():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_route'))
        
    form = LoginForm()
    if form.validate_on_submit():
        username_input = form.username.data.strip()
        password_input = form.password.data
        
        user_doc = db.users.find_one({"username": username_input})
        if user_doc and verify_password(password_input, user_doc["password"]):
            user_session = UserSession(user_doc)
            login_user(user_session)
            flash("Secure session tunnel bridged successfully.")
            return redirect(url_for('dashboard_route'))
            
        flash("Access Denied: Invalid signature credentials matching database registries.")
        
    return render_template('auth/login.html', form=form)

@app.route('/auth/logout')
@login_required
def logout_route():
    logout_user()
    flash("Session tunnel closed cleanly. Security credentials cleared.")
    return redirect(url_for('login_route'))

@app.route('/')
def landing_route():
    """Serves the central public dashboard portal frame."""
    return render_template('landing.html')

@app.route('/dashboard')
@login_required
def dashboard_route():
    """Serves the central upload terminal interface matrix."""
    return render_template('dashboard.html')

@app.route('/admin')
@login_required
def admin_dashboard_route():
    """Admin control panel with full access to all premium features and user management."""
    if current_user.role != 'Admin':
        flash("Administrator access required.")
        return redirect(url_for('dashboard_route'))

    users = list(db.users.find({}, {"password": 0, "verification_token": 0}))
    for user in users:
        user["_id"] = str(user["_id"])

    return render_template('admin.html', users=users)

@app.route('/premium-hub')
@login_required
def premium_hub_route():
    """Redirects to dashboard with premium upgrade overlay."""
    return redirect(url_for('dashboard_route') + '?upgrade=premium')

@app.route('/api/upload-csv', methods=['POST'])
@login_required
def upload_csv_api():
    """Ingests raw file text rows into separate supplier document folders inside MongoDB."""
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file container submitted."}), 400
        
    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return jsonify({"success": False, "message": "No chosen file target."}), 400

    # Capture filename for tracking
    original_filename = uploaded_file.filename
    max_filename_len = 120
    if len(original_filename) > max_filename_len:
        original_filename = original_filename[:max_filename_len]

    try:
        # Clear any previous cancel flags when a new upload begins
        try:
            db.system_control.update_one({"_id": "scan_control"}, {"$set": {"cancel_scan": False}}, upsert=True)
        except Exception:
            pass
        if request.content_length and request.content_length > 6 * 1024 * 1024:
            return jsonify({"success": False, "message": "File too large. Upload files under 6MB for analysis."}), 413

        raw_text = uploaded_file.stream.read().decode("UTF8", errors="ignore")
        if len(raw_text.encode('utf-8')) > MAX_CSV_BYTES:
            return jsonify({"success": False, "message": "Dataset too large for analysis. Split into smaller batches."}), 413

        stream = io.StringIO(raw_text, newline=None)
        df = pd.read_csv(stream, dtype=str, keep_default_na=False, na_values=[""])
        df.columns = [_normalize_csv_header(c) for c in df.columns]
        df = df.where(pd.notnull(df), None)

        _validate_csv_payload(df)

        # Aggregate rows by supplier name so data is not overwritten
        supplier_groups = {}
        for index, row in df.iterrows():
            normalized_row = row.to_dict()
            supplier_payload = _load_supplier_row(normalized_row, index)
            s_name = supplier_payload["name"]
            
            if s_name not in supplier_groups:
                # First row for this supplier: deep-copy key fields
                supplier_groups[s_name] = supplier_payload
                supplier_groups[s_name]["raw_rows"] = [supplier_payload["raw_columns"]]
                # Keep the delivery history from this first row
                supplier_groups[s_name]["delivery_history"] = supplier_payload.get("delivery_history", [100.0])
            else:
                # Subsequent rows: append raw data, aggregate numeric fields
                supplier_groups[s_name]["raw_rows"].append(supplier_payload["raw_columns"])
                # Append delivery history values
                if supplier_payload.get("delivery_history"):
                    supplier_groups[s_name]["delivery_history"].extend(supplier_payload["delivery_history"])
                # Update hazard score to max of all rows
                existing_score = supplier_groups[s_name].get("hazard_score", 0.0)
                new_score = supplier_payload.get("hazard_score", 0.0)
                supplier_groups[s_name]["hazard_score"] = max(existing_score, new_score)

        # Now insert/update aggregated suppliers
        for s_name, aggregated in supplier_groups.items():
            # Calculate average delivery history
            dh = aggregated.get("delivery_history", [100.0])
            avg_rate = sum(dh) / len(dh) if dh else 100.0
            aggregated["overall_on_time_rate"] = round(avg_rate, 2)
            aggregated["delivery_history"] = dh[-10:]  # Keep last 10 entries
            
            db.suppliers.update_one(
                {"name": s_name},
                {"$set": aggregated},
                upsert=True
            )
            
        analysis_thread = threading.Thread(
            target=run_analysis_in_background,
            args=(current_user.tier,)
        )
        analysis_thread.start()
        
        # Save scan history record
        try:
            supplier_count = len(supplier_groups)
            history_entry = {
                "filename": original_filename,
                "uploaded_by": current_user.username,
                "uploaded_at": datetime.now(timezone.utc),
                "supplier_count": supplier_count,
                "status": "Processing"
            }
            db.scan_history.insert_one(history_entry)
        except Exception:
            pass

        return jsonify({"success": True, "message": f"Upload accepted. Found {len(supplier_groups)} supplier(s) from {len(df)} data rows. Analysis engine will normalize your data."})
        
    except ValueError as err:
        return jsonify({"success": False, "message": str(err)}), 400
    except Exception as err:
        return jsonify({"success": False, "message": str(err)}), 500


@app.route('/api/scan-cancel', methods=['POST'])
@login_required
def scan_cancel_api():
    """Client requested cancel: mark control flag and set in-flight supplier docs to Cancelled."""
    try:
        # Mark global cancel flag
        db.system_control.update_one({"_id": "scan_control"}, {"$set": {"cancel_scan": True}}, upsert=True)
        # Update supplier docs currently pending/analyzing to Cancelled
        db.suppliers.update_many(
            {"processing_status": {"$in": ["Pending", "Analyzing"]}},
            {"$set": {"processing_status": "Cancelled", "ai_risk_summary": "Analysis cancelled by user."}}
        )
        return jsonify({"success": True, "message": "Scan cancel requested."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/scan-clear', methods=['POST'])
@login_required
def scan_clear_api():
    """Clear any cancel flag when starting a new upload/session."""
    try:
        db.system_control.update_one({"_id": "scan_control"}, {"$set": {"cancel_scan": False}}, upsert=True)
        return jsonify({"success": True, "message": "Scan control cleared."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/scan-clear-and-return', methods=['POST'])
@login_required
def scan_clear_and_return_api():
    """Deletes all supplier documents and allows going back to upload. Saves to scan history."""
    try:
        # Save a history marker for the cleared scan
        current_suppliers = list(db.suppliers.find({}, {"name": 1, "risk_status": 1, "hazard_score": 1}))
        if current_suppliers:
            summary_entry = {
                "filename": "Manual Clear - " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "uploaded_by": current_user.username,
                "uploaded_at": datetime.now(timezone.utc),
                "supplier_count": len(current_suppliers),
                "suppliers_snapshot": [
                    {"name": s["name"], "risk_status": s.get("risk_status"), "hazard_score": s.get("hazard_score")}
                    for s in current_suppliers
                ],
                "status": "Cleared"
            }
            db.scan_history.insert_one(summary_entry)

        # Delete all supplier documents
        db.suppliers.delete_many({})
        # Clear cancel flag
        db.system_control.update_one({"_id": "scan_control"}, {"$set": {"cancel_scan": False}}, upsert=True)
        return jsonify({"success": True, "message": "Fleet data cleared. Ready for new upload."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/scan-save', methods=['POST'])
@login_required
def scan_save_api():
    """Saves current scan data as a named snapshot for later viewing."""
    payload = request.get_json()
    snapshot_name = payload.get('name', '').strip()
    if not snapshot_name:
        return jsonify({"success": False, "message": "Please provide a name for the snapshot."}), 400

    try:
        suppliers_data = list(db.suppliers.find({}, {"historical_timeline": 0}))
        serialized_suppliers = []
        for s in suppliers_data:
            s["_id"] = str(s["_id"])
            # Convert datetime objects to ISO strings for JSON serialization
            for key, value in s.items():
                if isinstance(value, datetime):
                    s[key] = value.isoformat()
            serialized_suppliers.append(s)

        snapshot_entry = {
            "snapshot_name": snapshot_name,
            "uploaded_by": current_user.username,
            "uploaded_at": datetime.now(timezone.utc),
            "supplier_count": len(serialized_suppliers),
            "suppliers_snapshot": serialized_suppliers,
            "status": "Saved"
        }
        result = db.scan_history.insert_one(snapshot_entry)
        return jsonify({"success": True, "message": f"Snapshot '{snapshot_name}' saved successfully.", "id": str(result.inserted_id)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/scan-load/<snapshot_id>')
@login_required
def scan_load_api(snapshot_id):
    """Loads a saved snapshot and returns all suppliers data."""
    try:
        snapshot = db.scan_history.find_one({"_id": ObjectId(snapshot_id)})
        if not snapshot:
            return jsonify({"success": False, "message": "Snapshot not found."}), 404

        suppliers = snapshot.get("suppliers_snapshot", [])
        return jsonify({"success": True, "suppliers": suppliers, "snapshot_name": snapshot.get("snapshot_name", "Unknown")})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/scan-delete/<snapshot_id>', methods=['DELETE'])
@login_required
def scan_delete_api(snapshot_id):
    """Deletes a saved snapshot from scan history."""
    try:
        result = db.scan_history.delete_one({"_id": ObjectId(snapshot_id), "uploaded_by": current_user.username})
        if result.deleted_count > 0:
            return jsonify({"success": True, "message": "Snapshot deleted."})
        else:
            return jsonify({"success": False, "message": "Snapshot not found or access denied."}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/scan-history')
@login_required
def scan_history_api():
    """Returns scan history for the current user, including saved snapshots."""
    try:
        history = list(db.scan_history.find(
            {"uploaded_by": current_user.username},
        ).sort("uploaded_at", -1).limit(50))
        for h in history:
            h["_id"] = str(h["_id"])
            if isinstance(h.get("uploaded_at"), datetime):
                h["uploaded_at"] = h["uploaded_at"].isoformat()
        return jsonify(history)
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "history": []}), 500

@app.route('/api/suppliers-list')
@login_required
def suppliers_list_api():
    """Serves compiled data directly to client side JavaScript polling queries."""
    vendors = list(db.suppliers.find({}, {"historical_timeline": 0})) # Drop heavy arrays to load instantly
    for v in vendors:
        v["_id"] = str(v["_id"]) # Cast BSON tracking ids into standard strings
    return jsonify(vendors)

from utils.background_worker import handle_compliance_chat
from MCP_tools.gitlab_tool import create_compliance_ticket
from MCP_tools.email_tool import send_security_alert_email

@app.route('/supplier/<supplier_id>')
@login_required
def supplier_detail_route(supplier_id):
    """Retrieves specific vendor parameters to serve the holographic dashboard deck."""
    supplier_doc = db.suppliers.find_one({"_id": ObjectId(supplier_id)})
    if not supplier_doc:
        flash("Node Error: Target document could not be matched inside active registries.")
        return redirect(url_for('dashboard_route'))
    supplier_doc["_id"] = str(supplier_doc["_id"])
    if not supplier_doc.get("historical_timeline"):
        supplier_doc["historical_timeline"] = []
    return render_template('supplier_detail.html', supplier=supplier_doc)

@app.route('/auth/upgrade-profile', methods=['POST'])
@login_required
def upgrade_profile_route():
    """Alters active configuration clearance flags from Free to Premium nodes."""
    if upgrade_user_tier(current_user.username):
        flash("Premium access enabled.")
        return redirect(url_for('dashboard_route'))
    else:
        flash("Upgrade transmission failed. Secure terminal handshake rejected.")
        return redirect(request.referrer)

@app.route('/api/chat-compliance', methods=['POST'])
@login_required
def chat_compliance_api():
    """Asynchronous pipeline channel connecting managers straight to chat engines."""
    payload = request.get_json()
    user_query = payload.get('query', '')
    vendor_name = payload.get('supplier_name', '')
    
    # Calls conversational connector module built in Phase 4
    ai_response = handle_compliance_chat(user_query, vendor_name)
    return jsonify({"answer": ai_response})

@app.route('/api/approve-gitlab-ticket/<supplier_id>', methods=['POST'])
@login_required
def approve_gitlab_ticket_api(supplier_id):
    """Executes the human confirmation signature to fire the GitLab ticket tool."""
    payload = request.get_json() or {}
    project_id = payload.get('project_id', '').strip()
    access_token = payload.get('access_token', '').strip() or None
    if not project_id:
        return jsonify({"success": False, "message": "GitLab Project ID is required."}), 400

    supplier_doc = db.suppliers.find_one({"_id": ObjectId(supplier_id)})
    
    if supplier_doc and supplier_doc.get("requires_ticket_approval"):
        # Fire the official tool function we loaded inside Phase 3
        tool_status = create_compliance_ticket(
            supplier_name=supplier_doc["name"],
            risk_reason=supplier_doc.get("ticket_reason", "Critical threat mitigation escalation."),
            project_id=project_id,
            access_token=access_token
        )
        
        # Clear the flag so the human approval panel doesn't display again
        db.suppliers.update_one(
            {"_id": ObjectId(supplier_id)},
            {"$set": {"requires_ticket_approval": False, "ticket_created": True}}
        )
        return jsonify({"message": tool_status})
        
    return jsonify({"message": "Action denied or ticket already dispatched."}), 400

# ==========================================
# PHASE 6: COMPREHENSIVE GRAPH DATA ENGINE ROUTE
# ==========================================
@app.route('/api/analytics/dashboard-charts')
@login_required
def dashboard_charts_api():
    """Generates the structured data matrices for all Phase 6 interactive visualization panels."""
    vendors = list(db.suppliers.find({}))
    
    # 1. BAR CHART: Hazard Score Distribution Buckets
    buckets = {"0-25 (Low)": 0, "26-50 (Medium)": 0, "51-75 (Elevated)": 0, "76-100 (Critical)": 0}
    for v in vendors:
        score = v.get("hazard_score", 0.0)
        if score <= 25: buckets["0-25 (Low)"] += 1
        elif score <= 50: buckets["26-50 (Medium)"] += 1
        elif score <= 75: buckets["51-75 (Elevated)"] += 1
        else: buckets["76-100 (Critical)"] += 1

    # 2. PIE CHART: Threat Allocation Profile Percentages
    status_ranks = [v.get("risk_status", "Low") for v in vendors]
    pie_data = {
        "Low Risk": status_ranks.count("Low"),
        "Medium Risk": status_ranks.count("Medium"),
        "High Risk": status_ranks.count("High")
    }

    # 3. HEATMAP: 3x3 Cross Matrix (Performance Index vs Hazard Level)
    heatmap_z = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    for v in vendors:
        score = v.get("hazard_score", 0.0)
        perf = v.get("overall_on_time_rate", 100.0)
        p_idx = 0 if perf >= 95 else (1 if perf >= 85 else 2) # High, Mid, Low Perf
        s_idx = 0 if score <= 35 else (1 if score <= 70 else 2) # Low, Mid, High Threat
        heatmap_z[p_idx][s_idx] += 1

    # 4. TIMELINE: Compliance Certification Deadlines
    timeline_labels = []
    timeline_dates = []
    base_date = datetime.now(timezone.utc)
    for i, v in enumerate(vendors[:6]): # Limit to first 6 for a clean layout
        timeline_labels.append(v["name"])
        # Simulated expiry timeline offset logs (e.g., +30 days, +60 days)
        expiry_sim = base_date + timedelta(days=(i * 45) + 30)
        timeline_dates.append(expiry_sim.strftime("%Y-%m-%d"))

    # 5. TREEMAP: Structural Supplier Tier Hierarchy Tree Nodes
    tree_labels = ["Total Fleet Supply Chain"]
    tree_parents = [""]
    tree_values = [len(vendors)]
    
    categories = set(v.get("category", "Logistics") for v in vendors)
    for cat in categories:
        tree_labels.append(cat)
        tree_parents.append("Total Fleet Supply Chain")
        tree_values.append(sum(1 for v in vendors if v.get("category") == cat))
        
        for v in vendors:
            if v.get("category") == cat:
                tree_labels.append(v["name"])
                tree_parents.append(cat)
                tree_values.append(1)

    # 6. GRAPH: Interconnected Network Node Matrix
    # Simulates link vectors mapping cross-dependencies between categories and vendors
    network_nodes = [{"id": "Hub-Alpha", "label": "Central Hub", "group": 1}]
    network_edges = []
    for v in vendors[:8]:
        network_nodes.append({"id": v["name"], "label": v["name"], "group": 2})
        network_edges.append({"source": "Hub-Alpha", "target": v["name"]})

    return jsonify({
        "bar_x": list(buckets.keys()), "bar_y": list(buckets.values()),
        "pie_labels": list(pie_data.keys()), "pie_values": list(pie_data.values()),
        "heatmap_z": heatmap_z,
        "timeline_x": timeline_dates, "timeline_y": timeline_labels,
        "tree_labels": tree_labels, "tree_parents": tree_parents, "tree_values": tree_values,
        "network_nodes": network_nodes, "network_edges": network_edges
    })

# ==========================================
# PHASE 7: CUSTOM AI DRAFTING & MCP DISPATCH
# ==========================================
@app.route('/api/analytics/draft-ai-ticket', methods=['POST'])
@login_required
def draft_ai_ticket_api():
    """Generates an automated, custom Markdown remediation ticket text via Gemini (Premium Tier)."""
    if not current_user_has_premium_access():
        return jsonify({"success": False, "message": "Feature locked. Premium license subscription needed."}), 403

    payload = request.get_json()
    supplier_name = payload.get('supplier_name', '').strip()
    if not supplier_name:
        return jsonify({"success": False, "message": "No supplier target provided."}), 400

    names_list = [s.strip() for s in supplier_name.split(',') if s.strip()]

    # Try exact name match first, then email, then case-insensitive regex
    nodes = list(db.suppliers.find({"name": {"$in": names_list}}))
    if not nodes:
        nodes = list(db.suppliers.find({"contact_email": {"$in": names_list}}))
    if not nodes:
        import re
        patterns = [re.compile(f'^{re.escape(n)}$', re.IGNORECASE) for n in names_list]
        nodes = list(db.suppliers.find({"name": {"$in": patterns}}))

    try:
        # Construct custom analyst instructions using data variables from MongoDB
        query_context = "Compose an enterprise-grade GitLab incident issue ticket description tracking the following suppliers:\n"
        if nodes:
            for node in nodes:
                query_context += (
                    f"- {node['name']} (Category: {node.get('category', 'Unknown')}, "
                    f"Country: {node.get('country', 'Unknown')}, "
                    f"Hazard: {node.get('hazard_score', 0)}/100, "
                    f"On-Time Rate: {node.get('overall_on_time_rate', 100)}%)\n"
                )
        else:
            # No DB record found — use raw names for a generic ticket
            for name in names_list:
                query_context += f"- {name}\n"
        query_context += (
            "Write a comprehensive markdown report listing explicit operational vectors exposed, risk abstract details, "
            "and include 3 distinct smart pipeline mitigation steps to assign to the engineering response crew."
        )

        primary_name = nodes[0]['name'] if nodes else (names_list[0] if names_list else "Supplier")
        ai_draft_response = handle_compliance_chat(query_context, "Multiple Suppliers" if len(names_list) > 1 else primary_name)
        return jsonify({"success": True, "ai_markdown_draft": ai_draft_response})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/analytics/dispatch-bulk-remediation', methods=['POST'])
@login_required
def dispatch_bulk_remediation_api():
    """Executes official MCP tool functions to build issues in the GitLab tracker repository."""
    payload = request.get_json()
    
    # 1. Capture the NEW dynamic fields from your form
    project_id = payload.get('project_id')
    access_token = payload.get('access_token', '').strip() or None
    title = payload.get('title')
    category = payload.get('category')
    severity = payload.get('severity')
    supplier_name = payload.get('supplier_name')
    custom_content = payload.get('ticket_content', 'Escalation dispatch.')

    if not project_id or not project_id.strip():
        return jsonify({"success": False, "message": "GitLab Project ID is required."}), 400

    try:
        tool_status_message = create_compliance_ticket(
            supplier_name=supplier_name,
            risk_reason=custom_content,
            project_id=project_id.strip(),
            title=title,           # New parameter
            category=category,     # New parameter
            severity=severity,     # New parameter
            access_token=access_token # New parameter
        )
        
        # 3. Mark flags in database
        names_list = [s.strip() for s in supplier_name.split(',')]
        db.suppliers.update_many(
            {"name": {"$in": names_list}},
            {"$set": {"requires_ticket_approval": False, "ticket_created": True}}
        )
        return jsonify({"success": True, "message": f"Remediation Dispatch Confirmed: {tool_status_message}"})
        
    except Exception as err:
        return jsonify({"success": False, "message": f"GitLab MCP Tool Execution Failure: {str(err)}"}), 500
@app.route('/api/analytics/dispatch-all-high-risk', methods=['POST'])
@login_required
def dispatch_all_high_risk_api():
    """Creates GitLab remediation tickets for every high-risk supplier in one batch."""
    payload = request.get_json() or {}
    project_id = payload.get('project_id', '').strip()
    access_token = payload.get('access_token', '').strip() or None
    if not project_id:
        return jsonify({"success": False, "message": "GitLab Project ID is required."}), 400

    high_risk_nodes = list(db.suppliers.find({"risk_status": "High"}))
    if not high_risk_nodes:
        return jsonify({"success": True, "message": "All clear — no high-risk suppliers to dispatch.", "count": 0})

    dispatched = 0
    for node in high_risk_nodes:
        ticket_body = (
            f"### Auto-Escalation: {node['name']}\n\n"
            f"Hazard Index: {node.get('hazard_score', 0)}/100\n"
            f"On-Time Rate: {node.get('overall_on_time_rate', 100)}%\n"
            f"Region: {node.get('country', 'Unknown')}\n\n"
            "Immediate audit and corrective action required."
        )
        try:
            res = create_compliance_ticket(
                supplier_name=node["name"],
                risk_reason=ticket_body,
                project_id=project_id,
                access_token=access_token
            )
            if "Success" in res:
                db.suppliers.update_one(
                    {"name": node["name"]},
                    {"$set": {"requires_ticket_approval": False, "ticket_created": True}}
                )
                dispatched += 1
        except Exception:
            continue

    return jsonify({
        "success": True,
        "message": f"Bulk dispatch complete — {dispatched} GitLab ticket(s) created.",
        "count": dispatched
    })

# ==========================================
# PHASE 7 - EMAIL SENDING & AUDIT LOGGING
# ==========================================
@app.route('/api/analytics/get-email-recipients')
@login_required
def get_email_recipients_api():
    """Compiles contact parameters for all high-risk suppliers to load selection arrays."""
    high_risk_vendors = list(db.suppliers.find({"risk_status": "High"}))
    recipients = []
    for v in high_risk_vendors:
        recipients.append({
            "name": v["name"],
            "email": v.get("contact_email", "compliance@supplyshield.io"),
            "category": v.get("category", "General"),
            "hazard_score": v.get("hazard_score", 0.0)
        })
    return jsonify(recipients)

@app.route('/api/analytics/draft-ai-email', methods=['POST'])
@login_required
def draft_ai_email_api():
    """Instructs Gemini to draft a formal remediation warning alert message (Premium Tier)."""
    if not current_user_has_premium_access():
        return jsonify({"success": False, "message": "Feature locked. Premium license subscription required."}), 403

    payload = request.get_json()
    supplier_name = payload.get('supplier_name', '').strip()
    if not supplier_name:
        return jsonify({"success": False, "message": "No supplier target provided."}), 400

    names_list = [s.strip() for s in supplier_name.split(',') if s.strip()]
    
    # Try exact name match first, then email, then case-insensitive regex
    nodes = list(db.suppliers.find({"name": {"$in": names_list}}))
    if not nodes:
        nodes = list(db.suppliers.find({"contact_email": {"$in": names_list}}))
    if not nodes:
        # Case-insensitive fallback
        import re
        patterns = [re.compile(f'^{re.escape(n)}$', re.IGNORECASE) for n in names_list]
        nodes = list(db.suppliers.find({"name": {"$in": patterns}}))

    try:
        query_context = "Write a formal compliance alert notice email to the following suppliers:\n"
        if nodes:
            for node in nodes:
                query_context += (
                    f"- {node['name']} (Category: {node.get('category', 'Unknown')}, "
                    f"Hazard Index: {node.get('hazard_score', 0)}/100, "
                    f"On-Time Rate: {node.get('overall_on_time_rate', 100)}%)\n"
                )
        else:
            # No DB record found — use the raw names provided and generate a generic alert
            for name in names_list:
                query_context += f"- {name}\n"
        query_context += (
            "Demand immediate corrective logs regarding these supply bottlenecks, "
            "mention professional service legal requirements, and keep the tone urgent yet executive."
        )
        primary_name = nodes[0]['name'] if nodes else (names_list[0] if names_list else "Supplier")
        ai_email_response = handle_compliance_chat(query_context, "Multiple Suppliers" if len(names_list) > 1 else primary_name)
        return jsonify({"success": True, "ai_email_draft": ai_email_response})
    except Exception as err:
        return jsonify({"success": False, "message": str(err)}), 500

@app.route('/api/analytics/send-alert-email', methods=['POST'])
@login_required
def send_alert_email_api():
    """Dispatches the alert transmission and creates persistent records inside EmailAuditLog."""
    payload = request.get_json()
    supplier_name = payload.get('supplier_name', '')
    recipient_email = payload.get('recipient_email', '')
    email_body = payload.get('email_body', '')

    if not recipient_email or not email_body.strip():
        return jsonify({"success": False, "message": "Incomplete payload details."}), 400

    try:
        html_body = email_body.replace("\n", "<br>")
        subject = f"SupplyShield Compliance Alert — {supplier_name}"
        mcp_transmission_receipt = send_security_alert_email(recipient_email, subject, html_body)
        delivered = "successfully" in mcp_transmission_receipt.lower()

        actual_supplier_name = supplier_name
        supplier_doc = db.suppliers.find_one({"name": supplier_name})
        if not supplier_doc:
            supplier_doc = db.suppliers.find_one({"contact_email": supplier_name})
            if supplier_doc:
                actual_supplier_name = supplier_doc["name"]

        audit_log_entry = {
            "supplier_name": actual_supplier_name,
            "recipient_email": recipient_email,
            "email_body": email_body,
            "sender_account": current_user.username,
            "dispatched_timestamp": datetime.now(timezone.utc),
            "status": "Delivered" if delivered else "Failed",
            "mcp_receipt_id": str(ObjectId())
        }
        db.EmailAuditLog.insert_one(audit_log_entry)

        if not delivered:
            return jsonify({"success": False, "message": mcp_transmission_receipt}), 502

        return jsonify({"success": True, "message": f"Communication complete! {mcp_transmission_receipt}"})
    except Exception as err:
        return jsonify({"success": False, "message": f"MCP Mail Server Refused Handshake: {str(err)}"}), 500

# ==========================================
# PHASE 8: DATA LOG LOGS EXPORT & AUDIT REPORTING
# ==========================================
@app.route('/api/export/suppliers-csv')
@login_required
def export_suppliers_csv_api():
    """Compiles MongoDB registries to stream back clean tabular CSV file spreadsheets."""
    export_filter_type = request.args.get('type', 'all')
    
    if export_filter_type == 'high_risk':
        query_condition = {"risk_status": "High"}
        filename_marker = "HighRisk_Suppliers"
    else:
        query_condition = {}
        filename_marker = "All_Suppliers"

    vendors_cursor = db.suppliers.find(query_condition, {"historical_timeline": 0, "_id": 0})
    vendors_list = list(vendors_cursor)

    if not vendors_list:
        # Prevent pandas crashes with a single fallback row container
        vendors_list = [{"StatusMessage": "No active vendor records inventory matching parameters verified inside data cloud ledger."}]

    # Convert mapping matrix straight to DataFrame tables
    df = pd.DataFrame(vendors_list)
    
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    return Response(
        csv_buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=SupplyShield_{filename_marker}_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@app.route('/api/export/compliance-pdf')
@login_required
def export_compliance_pdf_api():
    """Generates an executive-grade summary report listing fleet exposure logs (Premium Tier Gateway)."""
    if not current_user_has_premium_access():
        return jsonify({"success": False, "message": "Access Denied: Enterprise PDF compilation requires an active Premium verification token."}), 403

    try:
        all_tracked_nodes = list(db.suppliers.find({}))
        
        pdf_stream = io.BytesIO()
        doc = SimpleDocTemplate(pdf_stream, pagesize=letter,
                                rightMargin=54, leftMargin=54,
                                topMargin=54, bottomMargin=54)
        
        styles = getSampleStyleSheet()
        
        # Custom Paragraph styles
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#0c1524'), # premium dark slate
            spaceAfter=15
        )
        
        subtitle_style = ParagraphStyle(
            'DocSubTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#475569'),
            spaceAfter=25
        )
        
        h2_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#0055ff'), # premium cyan/blue
            spaceBefore=14,
            spaceAfter=10,
            keepWithNext=True
        )
        
        body_style = ParagraphStyle(
            'BodyDark',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=8
        )
        
        alert_style = ParagraphStyle(
            'AlertText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#991b1b')
        )
        
        story = []
        
        # 1. Header Title
        story.append(Paragraph("SUPPLYSHIELD-AI: ENTERPRISE REMEDIATION REPORT", title_style))
        story.append(Paragraph(f"Executive Security Audit  |  Runtime Stamp: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  Signer Node: {current_user.username}", subtitle_style))
        story.append(Spacer(1, 10))
        
        # 2. Summary grid box
        low_count = sum(1 for s in all_tracked_nodes if s.get('risk_status') == 'Low')
        med_count = sum(1 for s in all_tracked_nodes if s.get('risk_status') == 'Medium')
        high_count = sum(1 for s in all_tracked_nodes if s.get('risk_status') == 'High')
        
        summary_data = [
            [Paragraph("<b>Total System Vendors Tracked:</b>", body_style), Paragraph(str(len(all_tracked_nodes)), body_style)],
            [Paragraph("<b>Critical Threat Level (High Risk):</b>", body_style), Paragraph(f"<font color='#ef4444'><b>{high_count}</b></font>", body_style)],
            [Paragraph("<b>Average Calculated Hazard Index:</b>", body_style), Paragraph(f"{(sum(s.get('hazard_score', 0) for s in all_tracked_nodes)/len(all_tracked_nodes) if all_tracked_nodes else 0.0):.1f} / 100", body_style)]
        ]
        summary_table = Table(summary_data, colWidths=[220, 280])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('PADDING', (0,0), (-1,-1), 8),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(Paragraph("I. Executive Metrics Overview", h2_style))
        story.append(summary_table)
        story.append(Spacer(1, 15))
        
        # 3. High Risk alerts section with red borders
        story.append(Paragraph("II. High-Risk Vulnerability Red Flags", h2_style))
        high_risk_suppliers = [s for s in all_tracked_nodes if s.get('risk_status') == 'High']
        
        if not high_risk_suppliers:
            story.append(Paragraph("<b>✅ All Clear:</b> No high-risk compliance alerts registered in database registry.", body_style))
        else:
            for idx, s in enumerate(high_risk_suppliers):
                flag_text = (
                    f"<b>🚨 FLAG INCIDENT #{idx+1}: {s['name']}</b><br/>"
                    f"• Category Node: {s.get('category')}  |  Region Hub: {s.get('country')}<br/>"
                    f"• Performance On-Time Rate: {s.get('overall_on_time_rate')}%  |  Hazard score: <b>{s.get('hazard_score', 0)}/100</b><br/>"
                    f"• Root Cause Analysis: <i>{s.get('ai_risk_summary')}</i><br/>"
                    f"• Action Plan Directive: {s.get('smart_mitigation_steps')}"
                )
                flag_p = Paragraph(flag_text, alert_style)
                flag_table = Table([[flag_p]], colWidths=[500])
                flag_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fef2f2')),
                    ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor('#ef4444')),
                    ('PADDING', (0,0), (-1,-1), 10),
                ]))
                story.append(flag_table)
                story.append(Spacer(1, 12))
                
        story.append(Spacer(1, 10))
        
        # 4. Interactive table
        story.append(Paragraph("III. Complete Compliance Registry Index", h2_style))
        table_headers = ["Supplier", "Category", "Region", "On-Time Rate", "Hazard Index", "Status"]
        table_rows = [table_headers]
        for s in all_tracked_nodes:
            table_rows.append([
                s.get('name'),
                s.get('category'),
                s.get('country'),
                f"{s.get('overall_on_time_rate')}%",
                f"{s.get('hazard_score')}/100",
                s.get('risk_status')
            ])
            
        reg_table = Table(table_rows, colWidths=[120, 80, 80, 75, 75, 70])
        t_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0c1524')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('TOPPADDING', (0,0), (-1,0), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ])
        
        for r_idx in range(1, len(table_rows)):
            bg_col = colors.HexColor('#f8fafc') if r_idx % 2 == 0 else colors.white
            t_style.add('BACKGROUND', (0, r_idx), (-1, r_idx), bg_col)
            status = table_rows[r_idx][5]
            if status == 'High':
                t_style.add('TEXTCOLOR', (5, r_idx), (5, r_idx), colors.HexColor('#ef4444'))
                t_style.add('FONTNAME', (5, r_idx), (5, r_idx), 'Helvetica-Bold')
            elif status == 'Medium':
                t_style.add('TEXTCOLOR', (5, r_idx), (5, r_idx), colors.HexColor('#f59e0b'))
                t_style.add('FONTNAME', (5, r_idx), (5, r_idx), 'Helvetica-Bold')
            else:
                t_style.add('TEXTCOLOR', (5, r_idx), (5, r_idx), colors.HexColor('#10b981'))
                
        reg_table.setStyle(t_style)
        story.append(reg_table)
        
        # 5. Risk score bar chart
        story.append(Spacer(1, 15))
        story.append(Paragraph("IV. Threat Index Allocation Chart", h2_style))
        
        drawing = Drawing(400, 160)
        chart = VerticalBarChart()
        chart.x = 40
        chart.y = 25
        chart.height = 110
        chart.width = 320
        chart.data = [[low_count, med_count, high_count]]
        chart.categoryAxis.categoryNames = ['Low Risk', 'Medium Risk', 'High Risk']
        chart.categoryAxis.labels.boxAnchor = 'ne'
        chart.categoryAxis.labels.dx = 8
        chart.categoryAxis.labels.dy = -2
        chart.categoryAxis.labels.fontName = 'Helvetica'
        chart.categoryAxis.labels.fontSize = 8
        
        chart.bars[(0, 0)].fillColor = colors.HexColor('#10b981') # green
        chart.bars[(0, 1)].fillColor = colors.HexColor('#f59e0b') # orange
        chart.bars[(0, 2)].fillColor = colors.HexColor('#ef4444') # red
        
        chart.valueAxis.valueMin = 0
        max_val = max(low_count, med_count, high_count, 1)
        chart.valueAxis.valueMax = max_val + 1
        chart.valueAxis.valueStep = max(1, max_val // 3)
        
        drawing.add(chart)
        story.append(drawing)
        
        doc.build(story)
        pdf_stream.seek(0)
        
        return Response(
            pdf_stream.read(),
            mimetype="application/pdf",
            headers={"Content-disposition": f"attachment; filename=SupplyShield_Executive_Audit_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )
    except Exception as err:
        return jsonify({"success": False, "message": f"PDF Generation Failure: {str(err)}"}), 500

@app.route('/premium')
def premium_page():
    # Public Premium landing page describing features and pricing
    if current_user.is_authenticated:
        return render_template('premium.html')
    return render_template('premium.html')
# ==========================================
# SERVER RUNTIME INVOCATION ROOT BOOT
# ==========================================
if __name__ == '__main__':
    # Disabling the reloader fixes the "WinError 10038" and "finalizing" crashes
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)