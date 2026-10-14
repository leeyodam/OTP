"""
MFA service — TOTP enrollment and verification bound to legacy session cookies.
"""
import base64
import hashlib
import hmac
import io
import os
import secrets
import time
from functools import wraps
from typing import Optional, Tuple

import pyotp
import qrcode
import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    jsonify,
    make_response,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from storage import store

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("MFA_SECRET_KEY", "dev-mfa-secret")
app.config["SESSION_COOKIE_NAME"] = os.environ.get("MFA_SESSION_COOKIE_NAME", "mfa_session")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
secure = os.environ.get("MFA_COOKIE_SECURE", "false").lower() == "true"
app.config["SESSION_COOKIE_SECURE"] = secure

SERVICE_SHARED_SECRET = os.environ.get("SERVICE_SHARED_SECRET", "dev-shared-secret")
LEGACY_INTERNAL_URL = os.environ.get("LEGACY_INTERNAL_URL", "http://127.0.0.1:5000")
LEGACY_COOKIE_NAME = os.environ.get("LEGACY_SESSION_COOKIE_NAME", "legacy_session")
OTP_WINDOW = int(os.environ.get("MFA_OTP_WINDOW", "1"))
MAX_OTP_FAILURES = int(os.environ.get("MFA_MAX_OTP_FAILURES", "5"))
LOCK_SECONDS = int(os.environ.get("MFA_LOCK_SECONDS", "300"))
CSRF_SERIALIZER = URLSafeTimedSerializer(SERVICE_SHARED_SECRET, salt="mfa-csrf")

limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])

SETUP_TEMPLATE = """
<!DOCTYPE html>
<html><head><title>MFA Setup</title></head>
<body>
<h1>Register Google Authenticator</h1>
{% if demo_otp %}<p><strong>PoC test hint:</strong> you can enter <code>{{ demo_otp }}</code> instead of scanning.</p>{% endif %}
<p>Scan this QR code with Google Authenticator, then enter a code to confirm.</p>
<img src="data:image/png;base64,{{ qr_b64 }}" alt="QR code"/>
<form method="post">
  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
  <label>OTP <input name="otp" required autocomplete="one-time-code"></label>
  <button type="submit">Confirm enrollment</button>
  {% if demo_otp %}<button type="submit" name="auto_demo" value="1" formnovalidate>PoC: enroll with test OTP</button>{% endif %}
</form>
</body></html>
"""

VERIFY_TEMPLATE = """
<!DOCTYPE html>
<html><head><title>MFA Verify</title></head>
<body>
<h1>Two-factor verification</h1>
{% if demo_otp %}<p><strong>PoC test hint (disable in production):</strong> current OTP is <code>{{ demo_otp }}</code></p>{% endif %}
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
<form method="post">
  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
  <label>OTP <input name="otp" required autocomplete="one-time-code"></label>
  <button type="submit">Verify</button>
  {% if demo_otp %}<button type="submit" name="auto_demo" value="1" formnovalidate>PoC: verify with test OTP</button>{% endif %}
</form>
</body></html>
"""


def _legacy_binding_from_request() -> Optional[str]:
    raw = request.cookies.get(LEGACY_COOKIE_NAME)
    if not raw:
        return None
    return hmac.new(
        SERVICE_SHARED_SECRET.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()


def validate_legacy_session() -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (username, legacy_binding) if legacy session is valid, else (None, None).
    Uses legacy protected API with forwarded cookies — no MFA hooks in legacy login code.
    """
    cookie_val = request.cookies.get(LEGACY_COOKIE_NAME)
    if not cookie_val:
        return None, None
    binding = hmac.new(
        SERVICE_SHARED_SECRET.encode(), cookie_val.encode(), hashlib.sha256
    ).hexdigest()
    headers = {"Cookie": f"{LEGACY_COOKIE_NAME}={cookie_val}"}
    try:
        resp = requests.get(
            f"{LEGACY_INTERNAL_URL}/api/protected",
            headers=headers,
            timeout=3,
        )
    except requests.RequestException:
        return None, None
    if resp.status_code != 200:
        return None, None
    data = resp.json()
    return data.get("user"), binding


def csrf_token() -> str:
    return CSRF_SERIALIZER.dumps({"n": secrets.token_hex(8)})


def verify_csrf() -> bool:
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not token:
        return False
    try:
        CSRF_SERIALIZER.loads(token, max_age=3600)
        return True
    except (BadSignature, SignatureExpired):
        return False


def mfa_session_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("mfa_sid"):
            return redirect("/login")
        return f(*args, **kwargs)

    return wrapped


def _demo_otp(secret: str) -> Optional[str]:
    if os.environ.get("MFA_TEST_MODE", "").lower() != "true":
        return None
    return pyotp.TOTP(secret).now()


def _qr_for_user(user_rec) -> str:
    totp = pyotp.TOTP(user_rec.totp_secret)
    uri = totp.provisioning_uri(name=user_rec.username, issuer_name="LegacyPoC")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def ensure_mfa_session(username: str, legacy_binding: str, status: str) -> str:
    mfa_sid = session.get("mfa_sid")
    if not mfa_sid:
        mfa_sid = secrets.token_urlsafe(32)
        session["mfa_sid"] = mfa_sid
    session["username"] = username
    session["legacy_binding"] = legacy_binding
    store.bind_session(mfa_sid, username, legacy_binding, status)
    return mfa_sid


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "mfa-service"})


@app.route("/mfa/setup", methods=["GET", "POST"])
@limiter.limit(os.environ.get("MFA_RATE_LIMIT", "30 per minute"))
def mfa_setup():
    username, binding = validate_legacy_session()
    if not username:
        return redirect("/login")
    mfa_sid = ensure_mfa_session(username, binding, "MFA_PENDING")
    user_rec = store.get_user(username)
    if user_rec is None:
        secret = pyotp.random_base32()
        store.upsert_user_secret(username, secret)
        user_rec = store.get_user(username)

    if request.method == "POST":
        if not verify_csrf():
            abort(403)
        otp = request.form.get("otp", "").strip()
        if request.form.get("auto_demo") == "1" and _demo_otp(user_rec.totp_secret):
            otp = _demo_otp(user_rec.totp_secret) or otp
        totp = pyotp.TOTP(user_rec.totp_secret)
        if totp.verify(otp, valid_window=OTP_WINDOW):
            step = int(time.time() // 30)
            if store.totp_step_used(username, binding, step):
                return render_template_string(
                    SETUP_TEMPLATE,
                    qr_b64=_qr_for_user(user_rec),
                    csrf_token=csrf_token(),
                    demo_otp=_demo_otp(user_rec.totp_secret),
                ), 400
            store.mark_enrolled(username)
            store.clear_failures(username)
            store.set_verified(mfa_sid, step)
            return redirect("/dashboard")
        store.record_failure(username, MAX_OTP_FAILURES, LOCK_SECONDS)
        return render_template_string(
            SETUP_TEMPLATE,
            qr_b64=_qr_for_user(user_rec),
            csrf_token=csrf_token(),
            demo_otp=_demo_otp(user_rec.totp_secret),
        ), 400

    if user_rec.enrolled:
        return redirect("/mfa/verify")

    return render_template_string(
        SETUP_TEMPLATE,
        qr_b64=_qr_for_user(user_rec),
        csrf_token=csrf_token(),
        demo_otp=_demo_otp(user_rec.totp_secret),
    )


@app.route("/mfa/verify", methods=["GET", "POST"])
@limiter.limit(os.environ.get("MFA_RATE_LIMIT", "30 per minute"))
def mfa_verify():
    username, binding = validate_legacy_session()
    if not username:
        return redirect("/login")
    user_rec = store.get_user(username)
    if user_rec is None or not user_rec.enrolled:
        return redirect("/mfa/setup")

    mfa_sid = ensure_mfa_session(username, binding, "MFA_PENDING")

    if store.is_locked(username):
        return render_template_string(
            VERIFY_TEMPLATE,
            error="Too many failures. Try again later.",
            csrf_token=csrf_token(),
            demo_otp=_demo_otp(user_rec.totp_secret),
        ), 429

    if request.method == "POST":
        if not verify_csrf():
            abort(403)
        otp = request.form.get("otp", "").strip()
        if request.form.get("auto_demo") == "1" and _demo_otp(user_rec.totp_secret):
            otp = _demo_otp(user_rec.totp_secret) or otp
        totp = pyotp.TOTP(user_rec.totp_secret)
        step = int(time.time() // 30)
        if store.totp_step_used(username, binding, step):
            return render_template_string(
                VERIFY_TEMPLATE,
                error="OTP already used",
                csrf_token=csrf_token(),
                demo_otp=_demo_otp(user_rec.totp_secret),
            ), 400
        if totp.verify(otp, valid_window=OTP_WINDOW):
            store.clear_failures(username)
            store.set_verified(mfa_sid, step)
            return redirect("/dashboard")
        store.record_failure(username, MAX_OTP_FAILURES, LOCK_SECONDS)
        return render_template_string(
            VERIFY_TEMPLATE,
            error="Invalid OTP",
            csrf_token=csrf_token(),
            demo_otp=_demo_otp(user_rec.totp_secret),
        ), 400

    return render_template_string(
        VERIFY_TEMPLATE,
        error=None,
        csrf_token=csrf_token(),
        demo_otp=_demo_otp(user_rec.totp_secret),
    )


@app.route("/internal/auth-check")
def internal_auth_check():
    """
    Called by nginx auth_request. Never trusts client MFA headers.
    """
    # Strip spoofed headers if any downstream would see them
    username, binding = validate_legacy_session()
    if not username:
        return "", 401

    from flask.sessions import SecureCookieSessionInterface

    interface = SecureCookieSessionInterface()
    s = interface.open_session(app, request)
    if not s:
        return "", 403
    sid = s.get("mfa_sid")
    if not sid:
        return "", 403
    state = store.get_session(sid)
    if not state or state.status != "MFA_VERIFIED":
        return "", 403
    if state.username != username or state.legacy_binding != binding:
        return "", 403
    return "", 200


@app.route("/logout", methods=["GET", "POST"])
def mfa_logout():
    sid = session.get("mfa_sid")
    binding = session.get("legacy_binding")
    cookie_val = request.cookies.get(LEGACY_COOKIE_NAME)
    if sid:
        store.invalidate_session(sid)
    if binding:
        store.invalidate_by_legacy_binding(binding)
    session.clear()
    if cookie_val:
        try:
            requests.get(
                f"{LEGACY_INTERNAL_URL}/logout",
                headers={"Cookie": f"{LEGACY_COOKIE_NAME}={cookie_val}"},
                timeout=3,
                allow_redirects=False,
            )
        except requests.RequestException:
            pass
    resp = make_response(redirect("/login"))
    resp.set_cookie(LEGACY_COOKIE_NAME, "", expires=0)
    return resp


@app.route("/internal/test/totp-secret")
def test_totp_secret():
    """Test-only: return enrolled secret for current legacy session (never enable in production)."""
    if os.environ.get("MFA_TEST_MODE", "").lower() != "true":
        abort(404)
    username, _binding = validate_legacy_session()
    if not username:
        abort(401)
    rec = store.get_user(username)
    if not rec:
        return jsonify({"secret": None, "enrolled": False})
    return jsonify({"secret": rec.totp_secret, "enrolled": rec.enrolled})


@app.route("/internal/invalidate-legacy")
def invalidate_legacy():
    """Called when legacy session ends (optional hook via proxy)."""
    sig = request.headers.get("X-Internal-Signature", "")
    body = request.query_string.decode()
    expected = hmac.new(
        SERVICE_SHARED_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        abort(403)
    binding = request.args.get("binding")
    if binding:
        store.invalidate_by_legacy_binding(binding)
    return "", 204


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
