"""
MFA adapter — legacy session binding + TOTP via embedded PoC or privacyIDEA.
"""
import hashlib
import hmac
import os
import secrets
from functools import wraps
from typing import Optional, Tuple

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
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from backends import get_backend
from backends.embedded import EmbeddedBackend
from storage import session_store

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
CSRF_SERIALIZER = URLSafeTimedSerializer(SERVICE_SHARED_SECRET, salt="mfa-csrf")
MFA_BACKEND_NAME = os.environ.get("MFA_BACKEND", "embedded")

limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])

SETUP_TEMPLATE = """
<!DOCTYPE html>
<html><head><title>MFA Setup</title></head>
<body>
<h1>Register Google Authenticator</h1>
<p>Backend: {{ backend_name }}</p>
{% if demo_otp %}<p><strong>PoC test hint:</strong> <code>{{ demo_otp }}</code></p>{% endif %}
<p>Scan this QR code, then enter a code to confirm.</p>
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
<p>Backend: {{ backend_name }}</p>
{% if demo_otp %}<p><strong>PoC test hint:</strong> <code>{{ demo_otp }}</code></p>{% endif %}
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
<form method="post">
  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
  <label>OTP <input name="otp" required autocomplete="one-time-code"></label>
  <button type="submit">Verify</button>
  {% if demo_otp %}<button type="submit" name="auto_demo" value="1" formnovalidate>PoC: verify with test OTP</button>{% endif %}
</form>
</body></html>
"""


def validate_legacy_session() -> Tuple[Optional[str], Optional[str]]:
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
    return resp.json().get("user"), binding


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


def ensure_mfa_session(username: str, legacy_binding: str, status: str) -> str:
    mfa_sid = session.get("mfa_sid")
    if not mfa_sid:
        mfa_sid = secrets.token_urlsafe(32)
        session["mfa_sid"] = mfa_sid
    session["username"] = username
    session["legacy_binding"] = legacy_binding
    session_store.bind_session(mfa_sid, username, legacy_binding, status)
    return mfa_sid


def _verify_otp(backend, username: str, otp: str, binding: str, enroll: bool) -> bool:
    if isinstance(backend, EmbeddedBackend):
        if backend.is_locked(username):
            return False
        return backend.verify_otp(
            username, otp, enroll_step=enroll, binding_key=binding
        )
    return backend.verify_otp(username, otp, enroll_step=enroll)


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "mfa-adapter",
            "mfa_backend": MFA_BACKEND_NAME,
        }
    )


@app.route("/mfa/setup", methods=["GET", "POST"])
@limiter.limit(os.environ.get("MFA_RATE_LIMIT", "30 per minute"))
def mfa_setup():
    username, binding = validate_legacy_session()
    if not username:
        return redirect("/login")
    backend = get_backend()
    mfa_sid = ensure_mfa_session(username, binding, "MFA_PENDING")

    if request.method == "POST":
        if not verify_csrf():
            abort(403)
        otp = request.form.get("otp", "").strip()
        if request.form.get("auto_demo") == "1":
            hint = backend.demo_otp(username)
            if hint:
                otp = hint
        if _verify_otp(backend, username, otp, binding, enroll=True):
            session_store.set_verified(mfa_sid, username, binding)
            return redirect("/dashboard")
        qr_b64 = backend.provisioning_qr_b64(username)
        return render_template_string(
            SETUP_TEMPLATE,
            qr_b64=qr_b64,
            csrf_token=csrf_token(),
            demo_otp=backend.demo_otp(username),
            backend_name=MFA_BACKEND_NAME,
        ), 400

    if backend.is_enrolled(username):
        return redirect("/mfa/verify")

    qr_b64 = backend.provisioning_qr_b64(username)
    return render_template_string(
        SETUP_TEMPLATE,
        qr_b64=qr_b64,
        csrf_token=csrf_token(),
        demo_otp=backend.demo_otp(username),
        backend_name=MFA_BACKEND_NAME,
    )


@app.route("/mfa/verify", methods=["GET", "POST"])
@limiter.limit(os.environ.get("MFA_RATE_LIMIT", "30 per minute"))
def mfa_verify():
    username, binding = validate_legacy_session()
    if not username:
        return redirect("/login")
    backend = get_backend()
    if not backend.is_enrolled(username):
        return redirect("/mfa/setup")

    mfa_sid = ensure_mfa_session(username, binding, "MFA_PENDING")

    if isinstance(backend, EmbeddedBackend) and backend.is_locked(username):
        return render_template_string(
            VERIFY_TEMPLATE,
            error="Too many failures. Try again later.",
            csrf_token=csrf_token(),
            demo_otp=backend.demo_otp(username),
            backend_name=MFA_BACKEND_NAME,
        ), 429

    if request.method == "POST":
        if not verify_csrf():
            abort(403)
        otp = request.form.get("otp", "").strip()
        if request.form.get("auto_demo") == "1":
            hint = backend.demo_otp(username)
            if hint:
                otp = hint
        if _verify_otp(backend, username, otp, binding, enroll=False):
            session_store.set_verified(mfa_sid, username, binding)
            return redirect("/dashboard")
        return render_template_string(
            VERIFY_TEMPLATE,
            error="Invalid OTP",
            csrf_token=csrf_token(),
            demo_otp=backend.demo_otp(username),
            backend_name=MFA_BACKEND_NAME,
        ), 400

    return render_template_string(
        VERIFY_TEMPLATE,
        error=None,
        csrf_token=csrf_token(),
        demo_otp=backend.demo_otp(username),
        backend_name=MFA_BACKEND_NAME,
    )


@app.route("/internal/auth-check")
def internal_auth_check():
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
    state = session_store.get_session(sid)
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
        session_store.invalidate_session(sid)
    if binding:
        session_store.invalidate_by_legacy_binding(binding)
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
    if os.environ.get("MFA_TEST_MODE", "").lower() != "true":
        abort(404)
    if MFA_BACKEND_NAME != "embedded":
        return jsonify({"error": "only available with MFA_BACKEND=embedded"}), 404
    username, _ = validate_legacy_session()
    if not username:
        abort(401)
    backend = get_backend()
    if not isinstance(backend, EmbeddedBackend):
        abort(404)
    secret = backend.totp_secret_for_tests(username)
    enrolled = backend.is_enrolled(username)
    return jsonify({"secret": secret, "enrolled": enrolled})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
