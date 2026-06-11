import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_security_alert_email(recipient_email: str, subject_text: str, alert_body: str) -> str:
    """
    Exposed MCP Tool: Dispatches warning alerts to managers using your Gmail SMTP App Password.
    """
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    
    if not sender_email or not sender_password:
        return "Email configuration is incomplete. Missing SENDER_EMAIL or SENDER_PASSWORD tokens."
        
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject_text
    msg.attach(MIMEText(alert_body, 'html'))
    
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Secure connection channel using TLS encryption wrappers
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        
        return f"Alert notification email successfully dispatched to {recipient_email}."
    except Exception as e:
        return f"Error executing SMTP mail transmission connection: {str(e)}"