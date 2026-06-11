import os
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from db_config import get_db_connection
from dotenv import load_dotenv
load_dotenv()
# Tracking counter to protect your free NewsAPI developer limits
NEWS_API_CALL_COUNTER = 0

def _call_gemini_rest(api_key: str, prompt: str, response_mime_type: str = "text/plain", temperature: float = 0.7) -> str:
    """
    Calls the Gemini REST API directly using the provided API key and prompt.
    Returns the text response from the model.
    Handles gemini-2.5-flash which may include 'thought' parts before text.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": response_mime_type
        }
    }
    response = requests.post(url, json=payload, timeout=90)
    if response.status_code != 200:
        raise Exception(f"Gemini API returned status {response.status_code}: {response.text[:500]}")
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise Exception("Gemini API returned no candidates in response.")
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        raise Exception("Gemini API returned no parts in response.")
    # gemini-2.5-flash returns 'thought' parts first, then the actual text part
    # We need the last text part (skip thought parts)
    text_result = ""
    for part in parts:
        if "thought" in part and part["thought"]:
            continue  # Skip thinking/reasoning parts
        if "text" in part:
            text_result = part["text"]
    if not text_result and parts:
        # Fallback: just take the last part's text
        text_result = parts[-1].get("text", "")
    return text_result


def fetch_external_news(supplier_name: str, country: str, category: str) -> list:
    """
    Queries live breaking web media reports for violations, shortages, or fraud.
    Enforces a hard limit of 100 maximum calls per day.
    """
    global NEWS_API_CALL_COUNTER
    if NEWS_API_CALL_COUNTER >= 100:
        print("⚠️ NewsAPI daily free tier threshold reached. Skipping live news queries.")
        return []
        
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return []
        
    search_query = f'("{supplier_name}" OR ("{country}" AND "{category}")) AND (fraud OR violation OR shortage OR risk)'
    url = f"https://newsapi.org/v2/everything?q={search_query}&language=en&pageSize=3&apiKey={api_key}"
    
    try:
        NEWS_API_CALL_COUNTER += 1
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            return response.json().get("articles", [])
    except Exception:
        pass 
    return []


def run_analysis_in_background(user_tier: str = "Free"):
    """
    Targets a native isolated background thread.
    Audits all 'Pending' status database manifests, computes dynamic moving average numbers,
    gates text blocks by account tier, and sets human approval flags for high-threat elements.
    """
    db = get_db_connection()
    api_key = os.getenv("GEMINI_API_KEY")
    # Check a global cancel flag before starting
    control = db.system_control.find_one({"_id": "scan_control"}) or {}
    if control.get("cancel_scan"):
        print("Scan cancelled before worker start. Aborting background analysis.")
        return

    # Clean any hidden formatting artifacts from the key
    gemini_ready = False
    if api_key:
        api_key = api_key.strip().replace('"', '').replace("'", "")
        gemini_ready = True
    
    if not gemini_ready:
        print("⚠️ No valid Gemini API key. Using statistical risk calculation from CSV data only.")
    pending_items = list(db.suppliers.find({"processing_status": "Pending"}))

    # If no Gemini, use local statistical analysis
    USE_LOCAL_FALLBACK = not gemini_ready
    MAX_WORKERS = 5  # Process 5 suppliers simultaneously

    def _analyze_single_supplier(supplier):
        """Analyze a single supplier — designed to run in a thread."""
        db_thread = get_db_connection()  # Each thread needs its own DB connection
        s_id = supplier["_id"]
        s_name = supplier["name"]
        use_fallback = USE_LOCAL_FALLBACK  # Local copy per thread

        # Check cancel flag
        control = db_thread.system_control.find_one({"_id": "scan_control"}) or {}
        if control.get("cancel_scan"):
            print(f"Scan cancelled, skipping {s_name}.")
            return

        db_thread.suppliers.update_one({"_id": s_id}, {"$set": {"processing_status": "Analyzing"}})

        try:
            # 1. Extract news packets
            articles = fetch_external_news(s_name, supplier["country"], supplier["category"])
            news_stream_text = "\n".join([f"- {a['title']}: {a['description']}" for a in articles]) if articles else "No urgent breaking public events found."

            # Compute delivery performance from raw CSV fields
            raw = supplier.get("raw_columns", {})
            delivery_history = supplier.get("delivery_history", [100.0])

            lead_time_val = _safe_float(raw.get("lead times"), raw.get("lead_times"))
            shipping_time_val = _safe_float(raw.get("shipping times"), raw.get("shipping_times"))
            defect_rate_val = _safe_float(raw.get("defect rates"), raw.get("defect_rates"))
            manufacturing_cost_val = _safe_float(raw.get("manufacturing costs"), raw.get("manufacturing_costs"))
            stock_level_val = _safe_float(raw.get("stock levels"), raw.get("stock_levels"))
            availability_val = _safe_float(raw.get("availability"))
            order_qty_val = _safe_float(raw.get("order quantities"), raw.get("order_quantities"))

            if lead_time_val is not None or defect_rate_val is not None or stock_level_val is not None:
                score = 100.0
                if lead_time_val is not None:
                    lead_penalty = min(30, max(0, (lead_time_val - 10) * 1.5))
                    score -= lead_penalty
                if defect_rate_val is not None:
                    defect_penalty = min(40, defect_rate_val * 8)
                    score -= defect_penalty
                if stock_level_val is not None:
                    if stock_level_val < 20: score -= 20
                    elif stock_level_val < 50: score -= 10
                if availability_val is not None:
                    if availability_val < 30: score -= 25
                    elif availability_val < 60: score -= 10
                if shipping_time_val is not None and shipping_time_val > 7:
                    score -= min(15, (shipping_time_val - 7) * 2)
                if manufacturing_cost_val is not None and manufacturing_cost_val > 80:
                    score -= 10
                delivery_history = [max(0, min(100, round(score, 2)))]

            # 2. Compute running average
            overall_moving_average = sum(delivery_history) / len(delivery_history)

            # 3. Generate monthly timeline data
            import random
            random.seed(hash(s_name))
            history_entries = []
            base = overall_moving_average
            for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]:
                base_drift = base + random.uniform(-5, 5)
                base_drift = max(0, min(100, base_drift))
                hs = max(0, min(100, 100 - base_drift + random.uniform(-10, 10)))
                history_entries.append({"month": m, "hazard_score": round(hs, 1), "on_time_rate": round(base_drift, 1)})

            # 4. Gemini / Local Analysis
            hazard_score = 0.0
            risk_status = "Low"
            ai_summary = "No analysis performed."
            mitigation = "No mitigation steps assigned."

            if not use_fallback:
                try:
                    extra_raw_fields = {
                        key: value for key, value in raw.items()
                        if key not in {
                            "name", "category", "country", "contact_email", "certifications",
                            "delivery_history", "overall_on_time_rate", "hazard_score", "risk_status",
                            "ai_risk_summary", "smart_mitigation_steps", "historical_timeline",
                            "last_checked", "processing_status", "stored_articles", "requires_ticket_approval",
                            "ticket_created", "ticket_reason", "_id"
                        }
                    }
                    extra_data_text = json.dumps(extra_raw_fields, default=str, ensure_ascii=False) if extra_raw_fields else "{}"
                    prompt_payload = f"""You are a supply chain risk analyst. Analyze this supplier and return a structured JSON risk assessment.

## SUPPLIER DATA
- Name: {s_name}
- Category: {supplier.get('category', 'Unknown')}
- Country: {supplier.get('country', 'Unknown')}
- Certifications: {', '.join(supplier.get('certifications', [])) or 'None listed'}
- Delivery Performance (avg on-time rate): {overall_moving_average:.1f}%
- Additional Data Fields: {extra_data_text}
- Recent News Mentions: {news_stream_text}

## SCORING RULES (follow strictly for consistency)
Calculate hazard_score (0-100) using this deterministic rubric:
- Delivery performance: below 70% = +35pts, 70-84% = +20pts, 85-94% = +8pts, 95%+ = +0pts
- Defect rate (if available): above 4% = +25pts, 2-4% = +12pts, 1-2% = +5pts
- Lead time (if available): above 25 days = +15pts, 15-25 days = +8pts
- Stock/availability (if available): below 30 = +12pts, 30-50 = +6pts
- Missing certifications or failed inspections: +15pts
- Negative news mentions found: +8pts per article (max +24pts)
- High-risk trade region (sanctioned countries, conflict zones): +10pts
- Cap the final score at 100.

Determine risk_status from hazard_score:
- 0-25: "Low"
- 26-55: "Medium"
- 56-100: "High"

## OUTPUT FORMAT
Return ONLY valid JSON with exactly these 4 keys:
{{
  "hazard_score": <float 0.0-100.0>,
  "risk_status": "Low" | "Medium" | "High",
  "ai_risk_summary": "<2-4 sentence professional analysis covering: key risk factors identified, data quality assessment, and overall supplier reliability. Be specific with numbers from the data. If Recent News Mentions indicate risk, you MUST explicitly mention them in this summary.>",
  "smart_mitigation_steps": "<Numbered list of 3-4 specific, actionable steps. Format: 1. [Action] — [Brief rationale]. Example: 1. Require updated ISO-9001 certification — Current certification status is unverified.>"
}}

Do NOT include any text outside the JSON object. Do NOT use markdown formatting."""

                    rest_response = _call_gemini_rest(
                        api_key=api_key,
                        prompt=prompt_payload,
                        response_mime_type="application/json",
                        temperature=0.0
                    )

                    cleaned_response = rest_response.strip()
                    if cleaned_response.startswith("```"):
                        cleaned_response = cleaned_response.split("\n", 1)[-1]
                        if cleaned_response.endswith("```"):
                            cleaned_response = cleaned_response[:-3].strip()

                    evaluation_map = json.loads(cleaned_response)
                    if not isinstance(evaluation_map, dict) or "hazard_score" not in evaluation_map:
                        raise ValueError("Gemini response did not return a valid analysis payload.")

                    hazard_score = max(0.0, min(100.0, float(evaluation_map.get("hazard_score", 0.0))))
                    risk_status = evaluation_map.get("risk_status", "Low")
                    if hazard_score > 55: risk_status = "High"
                    elif hazard_score > 25: risk_status = "Medium"
                    else: risk_status = "Low"

                    if user_tier == "Premium":
                        ai_summary = evaluation_map.get("ai_risk_summary", "No significant risks identified.")
                        mitigation = evaluation_map.get("smart_mitigation_steps", "Continue routine monitoring.")
                    else:
                        ai_summary = "🔒 Premium only: AI risk explanation"
                        mitigation = "🔒 Premium only: AI mitigation steps"
                except Exception as gemini_error:
                    print(f"Gemini analysis failed for {s_name}, using local fallback. Error: {gemini_error}")
                    use_fallback = True

            if use_fallback:
                # LOCAL FALLBACK: Statistical risk scoring without Gemini
                hazard_score = 0.0
                # 1. Low delivery performance = high hazard
                if overall_moving_average < 70:
                    hazard_score += 40
                elif overall_moving_average < 85:
                    hazard_score += 25
                elif overall_moving_average < 95:
                    hazard_score += 10
                # 2. High defect rates
                if defect_rate_val is not None:
                    if defect_rate_val > 4: hazard_score += 30
                    elif defect_rate_val > 2: hazard_score += 15
                    elif defect_rate_val > 1: hazard_score += 5
                # 3. High lead times
                if lead_time_val is not None:
                    if lead_time_val > 25: hazard_score += 20
                    elif lead_time_val > 15: hazard_score += 10
                # 4. Low availability/stock issues
                if availability_val is not None and availability_val < 30:
                    hazard_score += 15
                if stock_level_val is not None and stock_level_val < 20:
                    hazard_score += 15
                # 5. Certification/inspection issues
                cert_raw = supplier.get("certifications", [])
                if "fail" in str(cert_raw).lower() or (isinstance(cert_raw, list) and any("fail" in c.lower() for c in cert_raw)):
                    hazard_score += 25
                # 6. News risk
                if articles:
                    hazard_score += 5

                hazard_score = min(100, max(0, hazard_score))
                if hazard_score > 55: risk_status = "High"
                elif hazard_score > 25: risk_status = "Medium"
                else: risk_status = "Low"

                factors = []
                if defect_rate_val is not None and defect_rate_val > 1:
                    factors.append(f"Defect rate of {defect_rate_val:.1f}%")
                if lead_time_val is not None and lead_time_val > 15:
                    factors.append(f"Long lead time ({lead_time_val} days)")
                if overall_moving_average < 85:
                    factors.append(f"Low delivery performance ({overall_moving_average:.0f}%)")
                if stock_level_val is not None and stock_level_val < 30:
                    factors.append(f"Low stock level ({stock_level_val})")
                if articles:
                    news_titles = [a.get('title', '') for a in articles[:2] if a.get('title')]
                    if news_titles:
                        factors.append(f"Negative news found: {', '.join(news_titles)}")

                if factors:
                    ai_summary = "Risk factors detected: " + "; ".join(factors) + "."
                    mitigation = "1. Review and improve delivery performance. 2. Increase stock buffer levels. 3. Audit quality control processes. 4. Consider alternative suppliers."
                else:
                    ai_summary = "No significant risk indicators detected in available data."
                    mitigation = "Continue routine monitoring. All metrics within acceptable thresholds."

                if user_tier != "Premium":
                    ai_summary = "🔒 Premium only: " + ai_summary
                    mitigation = "🔒 Premium only: " + mitigation

            # === WRITE RESULTS TO DB ===
            current_month = datetime.now(timezone.utc).strftime("%Y-%m")
            snapshot_card = {
                "month": current_month,
                "hazard_score": hazard_score,
                "on_time_rate": delivery_history[-1],
                "risk_status": risk_status
            }

            db_thread.suppliers.update_one(
                {"_id": s_id},
                {
                    "$set": {
                        "overall_on_time_rate": round(overall_moving_average, 2),
                        "hazard_score": hazard_score,
                        "risk_status": risk_status,
                        "ai_risk_summary": ai_summary,
                        "smart_mitigation_steps": mitigation,
                        "stored_articles": articles,
                        "processing_status": "Completed",
                        "last_checked": datetime.now(timezone.utc)
                    },
                    "$push": {
                        "historical_timeline": snapshot_card
                    }
                }
            )

            # HIGH-THREAT ESCALATION FLAG
            if hazard_score > 55.0:
                db_thread.suppliers.update_one(
                    {"_id": s_id},
                    {
                        "$set": {
                            "requires_ticket_approval": True,
                            "ticket_created": False,
                            "ticket_reason": f"System Alert: Hazard score spiked to {hazard_score}. Summary: {ai_summary[:200]}"
                        }
                    }
                )

            print(f"✅ Completed: {s_name} (Score: {hazard_score}, Status: {risk_status})")

        except Exception as error_msg:
            print(f"❌ Analysis failed for {s_name}: {error_msg}")
            db_thread.suppliers.update_one(
                {"_id": s_id},
                {"$set": {"processing_status": "Failed", "ai_risk_summary": f"Analysis failed: {str(error_msg)[:200]}"}}
            )

    # === Execute parallel analysis ===
    from concurrent.futures import ThreadPoolExecutor, as_completed
    print(f"🚀 Starting parallel analysis of {len(pending_items)} suppliers with {MAX_WORKERS} workers...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_analyze_single_supplier, s): s["name"] for s in pending_items}
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"❌ Thread error for {name}: {e}")


def _safe_float(*values):
    """Return the first valid float from a list of values."""
    for v in values:
        if v is None:
            continue
        try:
            return float(v)
        except (ValueError, TypeError):
            continue
    return None


def handle_compliance_chat(user_query: str, target_supplier_name: str) -> str:
    """
    Conversational AI engine: Inspects database logs for a specific vendor,
    or falls back to a general workspace-wide assessment if no supplier is specified.
    """
    db = get_db_connection()
    
    if not target_supplier_name:
        # Workspace-wide AI assistant query: fetch summary of critical suppliers
        high_risk_list = list(db.suppliers.find({"risk_status": "High"}, {"name": 1, "category": 1, "country": 1, "hazard_score": 1}))
        # Clean ObjectId for serialization
        for item in high_risk_list:
            item["_id"] = str(item["_id"])

        context_stream = f"""You are SupplyShield-AI, a professional supply chain risk management assistant.

Your role: Help logistics managers understand and mitigate supply chain risks based on analyzed data.

Current high-risk suppliers in the system:
{json.dumps(high_risk_list, default=str, indent=2)}

Response guidelines:
- Be concise (2-4 sentences for simple questions, up to 6 for complex ones)
- Use specific numbers and data from the context when available
- Recommend actionable next steps when relevant
- If the question is outside your supply chain context, politely redirect
- Do NOT make up data not present in the context above"""
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return "AI assistant unavailable. Please configure the GEMINI_API_KEY in your environment."
            api_key = api_key.strip().replace('"', '').replace("'", "")
            result = _call_gemini_rest(
                api_key=api_key,
                prompt=f"{context_stream}\n\nManager's Question: {user_query}",
                temperature=0.3
            )
            return result
        except Exception as e:
            return f"AI assistant temporarily unavailable. Error: {str(e)}"
    else:
        supplier_record = db.suppliers.find_one({"name": target_supplier_name})
        if not supplier_record:
            return f"Supplier '{target_supplier_name}' not found in the database."
            
        extra_raw_fields = {
            key: value for key, value in supplier_record.get("raw_columns", {}).items()
            if key not in {
                "name", "category", "country", "contact_email", "certifications",
                "delivery_history", "overall_on_time_rate", "hazard_score", "risk_status",
                "ai_risk_summary", "smart_mitigation_steps", "historical_timeline",
                "last_checked", "processing_status", "stored_articles", "requires_ticket_approval",
                "ticket_created", "ticket_reason", "_id"
            }
        }
        extra_data_text = json.dumps(extra_raw_fields, default=str, ensure_ascii=False) if extra_raw_fields else "None"

        context_stream = f"""You are SupplyShield-AI, a supply chain compliance analyst. Answer questions about this specific supplier using ONLY the data provided below.

## Supplier Profile
- Name: {target_supplier_name}
- Category: {supplier_record.get('category', 'N/A')}
- Country: {supplier_record.get('country', 'N/A')}
- Hazard Score: {supplier_record.get('hazard_score', 0.0)}/100
- Risk Status: {supplier_record.get('risk_status', 'Low')}
- Delivery Performance: {supplier_record.get('overall_on_time_rate', 100)}%
- Certifications: {', '.join(supplier_record.get('certifications', [])) or 'None'}
- AI Risk Summary: {supplier_record.get('ai_risk_summary', 'Not yet analyzed')}
- Additional Data: {extra_data_text}
- Historical Timeline: {json.dumps(supplier_record.get('historical_timeline', []), default=str)}

## Response Guidelines
- Be precise and reference specific data points from the profile above
- Keep answers to 2-5 sentences unless the question requires more detail
- If asked about data not in the profile, clearly state it is not available
- Do NOT fabricate any information"""
    
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            api_key = api_key.strip().replace('"', '').replace("'", "")

            result = _call_gemini_rest(
                api_key=api_key,
                prompt=f"{context_stream}\n\nManager's Question: {user_query}",
                temperature=0.3
            )
            return result
        except Exception as e:
            return f"AI assistant temporarily unavailable. Error: {str(e)}"
