import os
import requests

def create_compliance_ticket(supplier_name: str, risk_reason: str, project_id: str = None, title: str = None, category: str = None, severity: str = None, access_token: str = None) -> str:
    """
    Exposed MCP Tool: Creates a security issue tracking ticket on GitLab.
    Supports dynamic project ID, title, category, and severity from dashboard form.
    """
    # 1. Pull environment tokens from your hidden vault (.env file)
    gitlab_url = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
    actual_project_id = project_id
    token = access_token or os.getenv("GITLAB_ACCESS_TOKEN")
    
    # Validation safety check if configuration is missing
    if not actual_project_id:
        return "GitLab Project ID is required. Please enter your GitLab Project ID in the form."
    if not token:
        return "GitLab configuration is incomplete. Missing GITLAB_ACCESS_TOKEN in .env file."
        
    # 2. Format the ticket headers and payload data packets
    url = f"{gitlab_url}/projects/{actual_project_id}/issues"
    headers = {"PRIVATE-TOKEN": token}
    
    # Build dynamic title
    issue_title = title or f"⚠️ COMPLIANCE ALERT: {supplier_name}"
    if severity and severity.lower() == "critical":
        issue_title = "🚨 " + issue_title
    
    # Build labels
    labels = "SupplyShield-AI, High-Risk-Vendor"
    if category:
        labels += f", {category}"
    if severity:
        labels += f", severity-{severity}"
    
    payload = {
        "title": issue_title,
        "description": f"Automated risk review required for {supplier_name}.\n\n**Reason for Alert:**\n{risk_reason}",
        "labels": labels
    }
    
    # 3. Post the request to GitLab's server pipeline
    try:
        print(f"[GitLab] Creating issue in project {actual_project_id}...")
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f"[GitLab] Response status: {response.status_code}")
        if response.status_code == 201:
            issue_data = response.json()
            print(f"[GitLab] Issue created: {issue_data.get('web_url')}")
            return f"Success! Compliance issue created on GitLab: {issue_data.get('web_url')}"
        else:
            print(f"[GitLab] Error response: {response.text[:500]}")
            return f"Failed to create GitLab issue (HTTP {response.status_code}): {response.text[:300]}"
    except requests.exceptions.Timeout:
        return f"GitLab API request timed out after 15 seconds. Check network connectivity."
    except Exception as e:
        print(f"[GitLab] Exception: {str(e)}")
        return f"Error connecting to GitLab system connection: {str(e)}"
