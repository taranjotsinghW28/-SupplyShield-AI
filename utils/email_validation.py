import re
import socket
import smtplib
import subprocess

def get_mx_records(domain: str) -> list:
    """Resolves MX records for a domain using the Windows native nslookup utility."""
    try:
        cmd = f"nslookup -type=mx {domain}"
        output = subprocess.check_output(cmd, shell=True, text=True, timeout=2)
        # Find MX hosts in nslookup output
        mx_records = re.findall(r"mail exchanger = ([\w\.-]+)", output)
        if mx_records:
            return [mx.strip() for mx in mx_records]
    except Exception as e:
        print(f"[SMTP Check] nslookup MX query failed: {e}")
    
    # Fallback to direct domain resolution
    return [domain]

def check_smtp_ping(email: str) -> bool:
    """
    Connects to the resolved MX server on port 25 and pings the mail server 
    to verify email existence. Includes an A-record fallback if Port 25 is blocked.
    """
    match = re.match(r"^[^@]+@([^@]+)$", email)
    if not match:
        return False
        
    domain = match.group(1)
    mx_hosts = get_mx_records(domain)
    if not mx_hosts:
        return False
        
    for host in mx_hosts:
        try:
            print(f"[SMTP Check] Connecting to mail exchanger {host} on port 25...")
            server = smtplib.SMTP(timeout=5)
            server.connect(host, 25)
            server.helo("supplyshield.io")
            server.mail("verify@supplyshield.io")
            code, message = server.rcpt(email)
            server.quit()
            
            print(f"[SMTP Check] Server response code: {code}")
            if code == 250:
                return True
            elif code == 550:
                # 550 is explicit: user does not exist
                return False
        except Exception as e:
            print(f"[SMTP Check] Failed to ping MX host {host}: {e}")
            continue
            
    # Fallback: If Port 25 was blocked or connection timed out on all mail exchangers,
    # perform an A-record domain lookup. If the domain is valid, pass the email registration.
    try:
        print(f"[SMTP Check] Outbound port 25 blocked. Checking if domain {domain} resolves...")
        socket.gethostbyname(domain)
        return True
    except Exception as dns_err:
        print(f"[SMTP Check] Domain {domain} does not resolve: {dns_err}")
        return False
