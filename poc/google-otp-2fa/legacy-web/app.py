"""
Legacy web server — ID/PW authentication only. No MFA awareness.
"""
import os
import time
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("LEGACY_SECRET_KEY", "dev-legacy-secret")
app.config["SESSION_COOKIE_NAME"] = os.environ.get(
    "LEGACY_SESSION_COOKIE_NAME", "legacy_session"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = int(
    os.environ.get("LEGACY_SESSION_LIFETIME_SECONDS", "3600")
)
secure = os.environ.get("LEGACY_COOKIE_SECURE", "false").lower() == "true"
app.config["SESSION_COOKIE_SECURE"] = secure

def _load_test_accounts() -> dict[str, str]:
    """
    PoC test users. Format: LEGACY_TEST_ACCOUNTS=user:pass,user2:pass2
    Default: testuser + test1..test5
    """
    raw = os.environ.get("LEGACY_TEST_ACCOUNTS", "").strip()
    if raw:
        accounts: dict[str, str] = {}
        for part in raw.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            username, password = part.split(":", 1)
            accounts[username.strip()] = password.strip()
        return accounts
    accounts = {
        os.environ.get("LEGACY_TEST_USER", "testuser"): os.environ.get(
            "LEGACY_TEST_PASSWORD", "TestPassword123!"
        ),
    }
    for i in range(1, 6):
        accounts[f"test{i}"] = f"test{i}!"
    return accounts


# Pre-hash passwords at startup (not MFA-related)
_ACCOUNT_PASSWORD_HASHES = {
    user: generate_password_hash(pw)
    for user, pw in _load_test_accounts().items()
}


def _verify_password(username: str, password: str) -> bool:
    digest = _ACCOUNT_PASSWORD_HASHES.get(username)
    if not digest:
        return False
    return check_password_hash(digest, password)

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html><head><title>Legacy Login</title></head>
<body>
<h1>Login</h1>
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
<form method="post" action="/login">
  <label>Username <input name="username" required></label><br>
  <label>Password <input name="password" type="password" required></label><br>
  <button type="submit">Sign in</button>
</form>
</body></html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html><head><title>Dashboard</title></head>
<body>
<h1>Protected Dashboard</h1>
<p>Welcome, {{ username }}.</p>
<p><a href="/logout">Logout</a></p>
</body></html>
"""


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "legacy-web"})


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect("/dashboard")
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if _verify_password(username, password):
            session.clear()
            session.permanent = True
            session["user"] = username
            session["login_at"] = int(time.time())
            session["sid"] = os.urandom(16).hex()
            next_url = request.args.get("next") or "/mfa/verify"
            return redirect(next_url)
        error = "Invalid username or password"
    return render_template_string(LOGIN_TEMPLATE, error=error)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template_string(DASHBOARD_TEMPLATE, username=session["user"])


@app.route("/api/protected")
@login_required
def api_protected():
    return jsonify(
        {
            "message": "protected resource",
            "user": session["user"],
            "session_id": session.get("sid"),
        }
    )


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
