"""Calculator API, hardened version.

The deliberately vulnerable variant of this file lives in security/vulnerable-sample/
and is what the scanners were first pointed at. See security/README.md.
"""
import os

from flask import Flask, jsonify, request

from app.calculator import calculate

APP_VERSION = os.getenv("APP_VERSION", "dev")

# Read from the environment. Never hardcode a credential in source: a committed
# secret lives in git history forever and is exactly what the secret-scanning
# stage of the pipeline looks for.
API_TOKEN = os.getenv("API_TOKEN", "")

app = Flask(__name__)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok", version=APP_VERSION)


@app.get("/")
def index():
    return jsonify(
        service="calculator-api",
        version=APP_VERSION,
        operations=sorted(["add", "subtract", "multiply", "divide"]),
        usage="/calc?op=add&a=10&b=5",
    )


@app.get("/calc")
def calc():
    op = request.args.get("op", "")
    try:
        a = float(request.args.get("a", ""))
        b = float(request.args.get("b", ""))
    except ValueError:
        return jsonify(error="a and b must be numbers"), 400

    # Dispatch through an explicit allow-list rather than eval(). The vulnerable
    # variant used eval(), which bandit flags as B307 and which lets a caller
    # execute arbitrary Python.
    try:
        return jsonify(operation=op, a=a, b=b, result=calculate(op, a, b))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@app.get("/whoami")
def whoami():
    """Confirms the token is sourced from the environment, without echoing it."""
    return jsonify(
        token_configured=bool(API_TOKEN),
        token_length=len(API_TOKEN),
    )


if __name__ == "__main__":
    # debug must stay off: the Werkzeug debugger exposes an interactive console
    # to anyone who can reach the app (bandit B201).
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
