"""
Minimal reverse-proxy harness for pytest when Docker/nginx is unavailable.
Mirrors nginx auth_request behavior from nginx/nginx.conf.
"""
import os
from urllib.parse import urljoin

import requests
from flask import Flask, Request, Response, request

LEGACY_URL = os.environ.get("TEST_LEGACY_URL", "http://127.0.0.1:5000")
MFA_URL = os.environ.get("TEST_MFA_URL", "http://127.0.0.1:5001")


def create_proxy_app() -> Flask:
    app = Flask(__name__)

    def forward(method: str, base: str, path: str, req: Request) -> Response:
        url = urljoin(base, path)
        headers = {k: v for k, v in req.headers if k.lower() != "host"}
        headers.pop("X-2FA-Verified", None)
        headers.pop("X-MFA-User", None)
        resp = requests.request(
            method,
            url,
            headers=headers,
            data=req.get_data(),
            cookies=req.cookies,
            allow_redirects=False,
            timeout=10,
        )
        excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        response_headers = [
            (k, v) for k, v in resp.headers.items() if k.lower() not in excluded
        ]
        return Response(resp.content, resp.status_code, response_headers)

    def mfa_auth_check(req: Request) -> int:
        r = requests.get(
            f"{MFA_URL}/internal/auth-check",
            headers={"Cookie": req.headers.get("Cookie", "")},
            timeout=5,
        )
        return r.status_code

    @app.route("/health")
    def health():
        return "ok", 200

    @app.route("/login", methods=["GET", "POST"])
    def login():
        return forward(request.method, LEGACY_URL, "/login", request)

    @app.route("/logout", methods=["GET", "POST"])
    def logout():
        return forward(request.method, MFA_URL, "/logout", request)

    @app.route("/mfa/<path:subpath>", methods=["GET", "POST"])
    def mfa(subpath):
        return forward(request.method, MFA_URL, f"/mfa/{subpath}", request)

    @app.route("/dashboard", methods=["GET"])
    def dashboard():
        code = mfa_auth_check(request)
        if code == 401:
            return Response(status=302, headers={"Location": "/login"})
        if code == 403:
            return Response(status=302, headers={"Location": "/mfa/verify"})
        return forward("GET", LEGACY_URL, "/dashboard", request)

    @app.route("/api/protected", methods=["GET"])
    def api_protected():
        code = mfa_auth_check(request)
        if code == 401:
            return Response('{"error":"unauthorized"}', status=401, mimetype="application/json")
        if code == 403:
            return Response(
                '{"error":"mfa_required"}', status=403, mimetype="application/json"
            )
        return forward("GET", LEGACY_URL, "/api/protected", request)

    return app


if __name__ == "__main__":
    create_proxy_app().run(host="127.0.0.1", port=18080, threaded=True)
