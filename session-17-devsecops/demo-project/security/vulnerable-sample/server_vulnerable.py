"""DELIBERATELY VULNERABLE. Not imported by the app, not shipped in the image.

This is the file I pointed the scanners at first, so the DevSecOps pipeline had
real findings to report instead of an empty clean run. Each issue below is one
the tooling actually flagged; security/README.md has the raw output and the fix.
"""
import os
import subprocess

from flask import Flask, jsonify, request

app = Flask(__name__)

# ISSUE 1 - hardcoded credential (bandit B105, and caught by gitleaks/trufflehog).
# A real token committed to git is readable by anyone who can clone the repo,
# and stays in the history even after it is "removed".
API_TOKEN = "ghp_R2d4kLm9QxT7vN1aB8cE3fH6jP0sW5yZ4uI2"
DB_PASSWORD = "SuperSecret123!"


@app.get("/calc")
def calc():
    expr = request.args.get("expr", "")
    # ISSUE 2 - eval on user input (bandit B307). Anyone can run arbitrary Python,
    # e.g. ?expr=__import__("os").system("cat /etc/passwd")
    return jsonify(result=eval(expr))


@app.get("/ping")
def ping():
    host = request.args.get("host", "127.0.0.1")
    # ISSUE 3 - shell injection (bandit B602 subprocess with shell=True).
    # ?host=1.1.1.1;rm -rf / runs both commands.
    out = subprocess.check_output(f"ping -c 1 {host}", shell=True)
    return out


@app.get("/read")
def read():
    name = request.args.get("name", "notes.txt")
    # ISSUE 4 - path traversal. ?name=../../etc/shadow escapes the directory.
    with open(os.path.join("/data", name)) as fh:
        return fh.read()


if __name__ == "__main__":
    # ISSUE 5 - debug mode on, bound to all interfaces (bandit B201, B104).
    # The Werkzeug debugger gives an interactive Python console to any caller.
    app.run(host="0.0.0.0", debug=True)
