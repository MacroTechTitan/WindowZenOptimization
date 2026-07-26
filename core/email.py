"""Email + contact-list integrations (Resend verification, SendGrid sync)."""
import os
import json
import urllib.request

from core.util import log_activity
from core.state import SITE_URL

try:
    import resend
    _RESEND_AVAILABLE = True
except ImportError:
    resend = None
    _RESEND_AVAILABLE = False


def get_resend_credentials():
    direct_key = os.environ.get("RESEND_API_KEY")
    if direct_key:
        return {
            "api_key": direct_key,
            "from_email": os.environ.get("RESEND_FROM_EMAIL", "noreply@macrotechtitan.com"),
        }
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")
    if not hostname:
        return None
    if repl_identity:
        token = "repl " + repl_identity
    elif web_repl_renewal:
        token = "depl " + web_repl_renewal
    else:
        return None
    try:
        req = urllib.request.Request(
            f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=resend",
            headers={"Accept": "application/json", "X-Replit-Token": token},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("items", [])
        if not items:
            return None
        settings = items[0].get("settings", {})
        return {
            "api_key": settings.get("api_key"),
            "from_email": settings.get("from_email") or "noreply@macrotechtitan.com",
        }
    except Exception as e:
        log_activity(f"Resend credentials error: {e}", "ERROR")
        return None


def send_verification_email(to_email, token):
    creds = get_resend_credentials()
    if not creds or not creds.get("api_key"):
        log_activity(f"Email not sent (no Resend creds) for {to_email}", "WARN")
        return False
    verify_url = f"{SITE_URL}/verify-email/{token}"
    from_addr = f"MTT Infinite Optimizer <{creds['from_email']}>"
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verify Your Email — MTT Infinite Optimizer</title>
<style>
  body{{margin:0;padding:0;background:#f4f6f9;font-family:'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased}}
  .outer{{padding:40px 16px}}
  .card{{max-width:520px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)}}
  .banner{{background:linear-gradient(135deg,#06b6d4 0%,#8b5cf6 100%);padding:36px 32px;text-align:center}}
  .banner-logo{{display:inline-block;background:rgba(255,255,255,0.15);border-radius:50px;padding:8px 20px;margin-bottom:16px}}
  .banner-logo span{{color:#fff;font-size:13px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase}}
  .banner h1{{margin:0;color:#ffffff;font-size:22px;font-weight:800;letter-spacing:0.3px}}
  .banner p{{margin:6px 0 0;color:rgba(255,255,255,0.78);font-size:13px}}
  .body{{padding:40px 36px}}
  .body p{{color:#374151;font-size:15px;line-height:1.75;margin:0 0 20px}}
  .body p.muted{{color:#6b7280;font-size:13px}}
  .divider{{height:1px;background:#e5e7eb;margin:24px 0}}
  .btn-wrap{{text-align:center;margin:28px 0}}
  .btn{{display:inline-block;background:linear-gradient(135deg,#10b981,#06b6d4);color:#ffffff;text-decoration:none;padding:16px 40px;border-radius:10px;font-size:16px;font-weight:700;letter-spacing:0.3px}}
  .url-box{{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:13px 16px;font-family:monospace;font-size:12px;color:#6b7280;word-break:break-all;margin-top:8px}}
  .features{{display:table;width:100%;border-collapse:separate;border-spacing:0}}
  .feat-row{{display:table-row}}
  .feat-cell{{display:table-cell;width:50%;vertical-align:top;padding:10px 8px}}
  .feat-item{{background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px}}
  .feat-item .icon{{font-size:20px;margin-bottom:6px}}
  .feat-item .label{{font-size:12px;font-weight:700;color:#111827;text-transform:uppercase;letter-spacing:0.5px}}
  .feat-item .desc{{font-size:12px;color:#6b7280;margin-top:2px}}
  .footer{{background:#f9fafb;border-top:1px solid #e5e7eb;padding:20px 36px;text-align:center}}
  .footer p{{margin:0;font-size:12px;color:#9ca3af;line-height:1.6}}
  .footer a{{color:#06b6d4;text-decoration:none}}
</style>
</head>
<body>
<div class="outer">
  <div class="card">

    <div class="banner">
      <div class="banner-logo"><span>⚡ Macro Tech Titan</span></div>
      <h1>MTT Infinite Optimizer</h1>
      <p>Windows System Utility v1.1.0</p>
    </div>

    <div class="body">
      <p>Hi there,</p>
      <p>Thanks for requesting a download of <strong>MTT Windows Infinite Optimizer v1.1.0</strong>. Click the button below to verify your email and unlock your free download link.</p>

      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px auto;">
        <tr>
          <td style="border-radius:10px;background:#10b981;text-align:center;">
            <a href="{verify_url}"
               target="_blank"
               style="display:inline-block;padding:16px 40px;font-size:16px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px;font-family:Helvetica,Arial,sans-serif;letter-spacing:0.3px;">
              ✅ &nbsp;Verify Email &amp; Get Download
            </a>
          </td>
        </tr>
      </table>

      <div class="divider"></div>

      <p class="muted"><strong>What you're getting:</strong></p>

      <table class="features" cellpadding="0" cellspacing="0">
        <tr>
          <td style="width:50%;padding:6px 6px 6px 0;vertical-align:top">
            <div class="feat-item">
              <div class="icon">📊</div>
              <div class="label">Health Score</div>
              <div class="desc">Real-time PC diagnostics</div>
            </div>
          </td>
          <td style="width:50%;padding:6px 0 6px 6px;vertical-align:top">
            <div class="feat-item">
              <div class="icon">🧹</div>
              <div class="label">Smart Cleaner</div>
              <div class="desc">Junk file removal</div>
            </div>
          </td>
        </tr>
        <tr>
          <td style="padding:6px 6px 0 0;vertical-align:top">
            <div class="feat-item">
              <div class="icon">🛡</div>
              <div class="label">Security Scan</div>
              <div class="desc">Cybersecurity checks</div>
            </div>
          </td>
          <td style="padding:6px 0 0 6px;vertical-align:top">
            <div class="feat-item">
              <div class="icon">⚡</div>
              <div class="label">Startup Boost</div>
              <div class="desc">Optimize boot speed</div>
            </div>
          </td>
        </tr>
      </table>

      <div class="divider"></div>

      <p class="muted">This link expires in <strong>7 days</strong>. If the button above doesn't work, copy and paste this URL into your browser:</p>
      <div class="url-box">{verify_url}</div>
    </div>

    <div class="footer">
      <p>You received this because you requested a download at<br>
      <a href="https://windowzen.macrotechtitan.com">windowzen.macrotechtitan.com</a><br><br>
      If you didn't request this, you can safely ignore this email.</p>
    </div>

  </div>
</div>
</body>
</html>"""
    try:
        if not _RESEND_AVAILABLE:
            log_activity("Resend not available (desktop mode) — skipping email send", "INFO")
            return False
        resend.api_key = creds["api_key"]
        result = resend.Emails.send({
            "from": from_addr,
            "to": [to_email],
            "subject": "⚡ Your MTT Infinite Optimizer Download Link",
            "html": html_body,
        })
        log_activity(f"Verification email sent → {to_email} (id:{getattr(result, 'id', '?')})", "SUCCESS")
        return True
    except Exception as e:
        log_activity(f"Failed to send email to {to_email}: {e}", "ERROR")
        return False


def add_to_sendgrid_list(email):
    api_key = os.environ.get("SENDGRID_API_KEY")
    list_id = os.environ.get("SENDGRID_LIST_ID")
    if not api_key:
        log_activity("SendGrid sync skipped — no API key", "WARN")
        return
    payload = {"contacts": [{"email": email}]}
    if list_id:
        payload["list_ids"] = [list_id]
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/marketing/contacts",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            log_activity(f"SendGrid contact added: {email} (status {resp.status})", "SUCCESS")
    except Exception as e:
        log_activity(f"SendGrid sync failed for {email}: {e}", "WARN")
