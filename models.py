from datetime import datetime, timezone, timedelta

SUBSCRIPTION_PERIOD_DAYS = 30

def create_user_model(username, email, hashed_password, role="Manager", tier="Free"):
    """Blueprint for secure user accounts with a default 'Free' tier."""
    return {
        "username": username,
        "email": email,
        "password": hashed_password,
        "role": role,
        "tier": tier,
        "created_at": datetime.now(timezone.utc) # <-- Modern Timezone-Aware UTC
    }

def create_supplier_model(name, category, country, tier=1, contact_email="", certifications=None, initial_delivery_rate=100.0):
    """
    Master blueprint for SupplyShield-AI tracking.
    Stores raw vendor info, continuous delivery arrays, and historical trend timelines.
    """
    current_month_stamp = datetime.now(timezone.utc).strftime("%Y-%m") # <-- Modern Timezone-Aware UTC
    
    # The first entry in our trend ledger
    initial_metrics = {
        "month": current_month_stamp,
        "hazard_score": 0.0,
        "on_time_rate": initial_delivery_rate,
        "risk_status": "Low"
    }

    return {
        # --- 1. CORE USER INPUTS ---
        "name": name,
        "category": category,
        "country": country,
        "tier": tier,
        "contact_email": contact_email,
        "certifications": certifications if certifications else [],
        
        # --- 2. DYNAMIC TRACKING ARRAYS (Python Math Engines) ---
        "delivery_history": [initial_delivery_rate],  # Stores individual monthly scores [95.0, 80.0, 100.0]
        "overall_on_time_rate": initial_delivery_rate, # Calculated running average of the array
        
        # --- 3. LIVE STATUS FIELDS (Overwritten by latest evaluations) ---
        "hazard_score": 0.0,          
        "risk_status": "Low",         
        "ai_risk_summary": "",        
        "smart_mitigation_steps": "", 
        
        # --- 4. THE GRAPH POWERHOUSE (Timeline Tracker) ---
        "historical_timeline": [initial_metrics], # Keeps historical snapshots for line charts
        
        # --- 5. SYSTEM METRICS ---
        "last_checked": datetime.now(timezone.utc), # <-- Modern Timezone-Aware UTC
        "processing_status": "Pending" 
    }

def create_audit_log_model(supplier_id, trigger_event, gemini_summary, changes_made):
    """Blueprint for permanent background automation history logs."""
    return {
        "supplier_id": supplier_id,
        "timestamp": datetime.now(timezone.utc), # <-- Modern Timezone-Aware UTC
        "trigger_event": trigger_event,
        "gemini_summary": gemini_summary,
        "changes_made": changes_made
    }