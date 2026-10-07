"""Small Flask wrapper so the calculator becomes something we can containerise and deploy."""
import os

from flask import Flask, jsonify, request

from app.calculator import calculate

APP_VERSION = os.getenv("APP_VERSION", "dev")

app = Flask(__name__)


@app.get("/healthz")
def healthz():
    """Liveness/readiness endpoint used by Kubernetes probes and by the CD smoke test."""
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

    try:
        return jsonify(operation=op, a=a, b=b, result=calculate(op, a, b))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
