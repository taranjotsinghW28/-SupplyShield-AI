from db_config import get_db_connection

def query_supplier_history(supplier_name: str) -> dict:
    """
    Exposed MCP Tool: Allows Gemini to pull down the past historical metric trends 
    for a specific vendor to perform deep analysis.
    """
    try:
        db = get_db_connection()
        supplier = db.suppliers.find_one({"name": supplier_name})
        
        if supplier:
            return {
                "name": supplier.get("name"),
                "overall_on_time_rate": supplier.get("overall_on_time_rate"),
                "historical_timeline": supplier.get("historical_timeline", [])
            }
        return {"error": f"No supplier found with name: {supplier_name}"}
    except Exception as e:
        return {"error": f"Database search error: {str(e)}"}

def write_analysis_summary(supplier_name: str, ai_summary: str, calculated_score: float, status: str) -> str:
    """
    Exposed MCP Tool: Allows Gemini to write its fresh final risk evaluations 
    directly back into the supplier database document.
    """
    try:
        db = get_db_connection()
        
        result = db.suppliers.update_one(
            {"name": supplier_name},
            {
                "$set": {
                    "hazard_score": calculated_score,
                    "risk_status": status,
                    "ai_risk_summary": ai_summary,
                    "processing_status": "Completed"
                }
            }
        )
        
        if result.matched_count > 0:
            return f"Successfully saved updated risk evaluation profiles for {supplier_name} to MongoDB."
        return f"No supplier found with name {supplier_name} to update."
    except Exception as e:
        return f"Database save error: {str(e)}"