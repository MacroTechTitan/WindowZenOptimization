"""Email registration gateway: signup, verification link, and download page."""
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, render_template, jsonify, request, redirect

from core.util import log_activity
from core.config import increment_analytics
from core.registrations import load_registrations, save_registrations, _reg_lock
from core.email import send_verification_email, add_to_sendgrid_list

bp = Blueprint("registration", __name__)


# ─── Email Registration Gateway ───────────────────────────────
@bp.route("/api/register-download", methods=["POST"])
def register_download():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Please enter a valid email address."}), 400
    with _reg_lock:
        registrations = load_registrations()
        existing = registrations.get(email)
        if existing and existing.get("verified"):
            send_verification_email(email, existing["token"])
            return jsonify({"ok": True, "resent": True, "message": "Already verified! Resent your download link."})
        if existing and not existing.get("verified"):
            token = existing["token"]
            registrations[email]["registered_at"] = datetime.utcnow().isoformat()
            save_registrations(registrations)
        else:
            token = str(uuid.uuid4())
            registrations[email] = {
                "token": token,
                "verified": False,
                "registered_at": datetime.utcnow().isoformat(),
                "verified_at": None,
                "ip": request.remote_addr or "unknown",
            }
            save_registrations(registrations)
    ok = send_verification_email(email, token)
    if not ok:
        return jsonify({"error": "Failed to send email. Please try again later."}), 500
    add_to_sendgrid_list(email)
    return jsonify({"ok": True, "message": "Verification email sent! Check your inbox."})


TOKEN_EXPIRY_DAYS = 7

@bp.route("/verify-email/<token>")
def verify_email(token):
    registrations = load_registrations()
    for email, info in registrations.items():
        if info.get("token") == token:
            if not info.get("verified"):
                try:
                    registered_at = datetime.fromisoformat(info.get("registered_at", ""))
                    if datetime.utcnow() - registered_at > timedelta(days=TOKEN_EXPIRY_DAYS):
                        return render_template("download.html", error="This link has expired (links are valid for 7 days). Please request a new one.", token=None, email=None)
                except Exception:
                    pass
                with _reg_lock:
                    registrations[email]["verified"] = True
                    registrations[email]["verified_at"] = datetime.utcnow().isoformat()
                    save_registrations(registrations)
                increment_analytics("downloads")
                log_activity(f"Email verified: {email} — download unlocked", "SUCCESS")
            return redirect(f"/download/{token}")
    return render_template("download.html", error="This link is invalid or has expired. Please request a new one.", token=None, email=None)


@bp.route("/download/<token>")
def download_page(token):
    registrations = load_registrations()
    for email, info in registrations.items():
        if info.get("token") == token and info.get("verified"):
            return render_template("download.html", error=None, token=token, email=email)
    return redirect("/")
