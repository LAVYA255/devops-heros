# Session 17: Complete CI/CD and DevSecOps

**Author:** Lavya ([@LAVYA255](https://github.com/LAVYA255))
**Course:** SST DevOps & Cloud [SWE]
**Session:** 17 - CI/CD + DevSecOps
**Repository:** `devops-heros / session-17-devsecops`

**This pipeline really runs.** All eight jobs executed on GitHub's hosted runners under my account.

- Workflow file: [`.github/workflows/session17-devsecops.yml`](../.github/workflows/session17-devsecops.yml)
- Application: [`session-17-devsecops/demo-project/`](./demo-project)
- Green run: https://github.com/LAVYA255/devops-heros/actions/runs/37647241010

Everything below was also run locally against both a hardened and a deliberately vulnerable version of the app, so the scanners have real findings to show rather than an empty clean sheet.

---

## The pipeline

```
 Code
  │
  ▼
 Build + Unit Test            flake8, pytest, coverage
  │
  ├──────────────┬──────────────────┐     three scanners, no dependency on each other,
  ▼              ▼                  ▼     so they run in parallel
 SAST           SCA            Secret Scan
 bandit         pip-audit      gitleaks
  │              │                  │
  └──────────────┴──────────────────┘
                 ▼
         Docker Build + Image Scan      trivy (vuln + secret + misconfig)
                 ▼
         ┌───────────────┐
         │ SECURITY GATE │   one explicit yes/no over all four results
         └───────┬───────┘
                 │  blocked -> publish and deploy are skipped
                 ▼
            Push to GHCR
                 ▼
        Deploy to Kubernetes           kind cluster, verify, confirm non-root
```

### Run result

![successful pipeline run](./screenshots/00-pipeline-run.jpg)

| Job | Tool | Result | Duration |
| --- | --- | --- | --- |
| Build and Unit Test | pytest, flake8 | success | 15s |
| SAST | bandit | success | 10s |
| SCA | pip-audit | success | 31s |
| Secret Scanning | gitleaks | success | 12s |
| Docker Build and Image Scan | trivy | success | 39s |
| Security Gate | - | success | 4s |
| Push to GHCR | - | success | 30s |
| Deploy to Kubernetes | kind | success | 1m 25s |

The three scanners started within two seconds of each other and finished independently.

---

## Giving the scanners something to find

A security pipeline that passes on day one teaches you nothing. So alongside the hardened app there is `demo-project/security/vulnerable-sample/`, which is never imported, never built into the image, and exists purely to be scanned:

- `server_vulnerable.py` with a hardcoded GitHub token, a hardcoded DB password, `eval()` on user input, `subprocess(..., shell=True)`, a path traversal, and `debug=True` bound to `0.0.0.0`
- `requirements-vulnerable.txt` pinning flask 0.12.2, jinja2 2.10, requests 2.19.1, urllib3 1.24.1, pyyaml 5.1
- `Dockerfile.vulnerable` on `python:3.6-slim`, with a secret baked into an `ENV` layer and no `USER` instruction

Every finding below is from actually pointing the tools at those files.

---

## 1. SAST, static application security testing

Reads the source and looks for insecure patterns. Bandit understands Python specifically.

**Output**
```text
# SAST = Static Application Security Testing. It reads the SOURCE and looks for insecure patterns.
# Point bandit at the deliberately vulnerable sample first, so we can see what it actually catches:
$ cat security/vulnerable-sample/server_vulnerable.py
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

$ docker run --rm -v /mnt/l/Devops/devops-heros/session-17-devsecops/demo-project:/src -w /src python:3.12-slim sh -c "pip install -q 'bandit[toml]==1.8.6' >/dev/null 2>&1; bandit -r security/vulnerable-sample --severity-level low" 2>&1 | sed -n '/Test results/,/Code scanned/p' | head -80
Test results:
>> Issue: [B404:blacklist] Consider possible security implications associated with the subprocess module.
   Severity: Low   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/blacklists/blacklist_imports.html#b404-import-subprocess
   Location: security/vulnerable-sample/server_vulnerable.py:8:0
7	import os
8	import subprocess
9

--------------------------------------------------
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'ghp_R2d4kLm9QxT7vN1aB8cE3fH6jP0sW5yZ4uI2'
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b105_hardcoded_password_string.html
   Location: security/vulnerable-sample/server_vulnerable.py:17:12
16	# and stays in the history even after it is "removed".
17	API_TOKEN = "ghp_R2d4kLm9QxT7vN1aB8cE3fH6jP0sW5yZ4uI2"
18	DB_PASSWORD = "SuperSecret123!"

--------------------------------------------------
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'SuperSecret123!'
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b105_hardcoded_password_string.html
   Location: security/vulnerable-sample/server_vulnerable.py:18:14
17	API_TOKEN = "ghp_R2d4kLm9QxT7vN1aB8cE3fH6jP0sW5yZ4uI2"
18	DB_PASSWORD = "SuperSecret123!"
19

--------------------------------------------------
>> Issue: [B307:blacklist] Use of possibly insecure function - consider using safer ast.literal_eval.
   Severity: Medium   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/blacklists/blacklist_calls.html#b307-eval
   Location: security/vulnerable-sample/server_vulnerable.py:26:26
25	    # e.g. ?expr=__import__("os").system("cat /etc/passwd")
26	    return jsonify(result=eval(expr))
27

--------------------------------------------------
>> Issue: [B602:subprocess_popen_with_shell_equals_true] subprocess call with shell=True identified, security issue.
   Severity: High   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b602_subprocess_popen_with_shell_equals_true.html
   Location: security/vulnerable-sample/server_vulnerable.py:34:10
33	    # ?host=1.1.1.1;rm -rf / runs both commands.
34	    out = subprocess.check_output(f"ping -c 1 {host}", shell=True)
35	    return out

--------------------------------------------------
>> Issue: [B201:flask_debug_true] A Flask app appears to be run with debug=True, which exposes the Werkzeug debugger and allows the execution of arbitrary code.
   Severity: High   Confidence: Medium
   CWE: CWE-94 (https://cwe.mitre.org/data/definitions/94.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b201_flask_debug_true.html
   Location: security/vulnerable-sample/server_vulnerable.py:49:4
48	    # The Werkzeug debugger gives an interactive Python console to any caller.
49	    app.run(host="0.0.0.0", debug=True)

--------------------------------------------------
>> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces.
   Severity: Medium   Confidence: Medium
   CWE: CWE-605 (https://cwe.mitre.org/data/definitions/605.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b104_hardcoded_bind_all_interfaces.html
   Location: security/vulnerable-sample/server_vulnerable.py:49:17
48	    # The Werkzeug debugger gives an interactive Python console to any caller.
49	    app.run(host="0.0.0.0", debug=True)

--------------------------------------------------

Code scanned:

$ docker run --rm -v /mnt/l/Devops/devops-heros/session-17-devsecops/demo-project:/src -w /src python:3.12-slim sh -c "pip install -q 'bandit[toml]==1.8.6' >/dev/null 2>&1; bandit -r security/vulnerable-sample -f json --severity-level low" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('%-9s %-11s %-7s %-55s %s' % ('SEVERITY','CONFIDENCE','TEST','ISSUE','LINE'))
for r in d['results']:
    print('%-9s %-11s %-7s %-55s %s' % (r['issue_severity'], r['issue_confidence'], r['test_id'], r['issue_text'][:55], r['line_number']))
m=d['metrics']['_totals']
print()
print('TOTALS  HIGH=%d MEDIUM=%d LOW=%d' % (m['SEVERITY.HIGH'], m['SEVERITY.MEDIUM'], m['SEVERITY.LOW']))
"
SEVERITY  CONFIDENCE  TEST    ISSUE                                                   LINE
LOW       HIGH        B404    Consider possible security implications associated with 8
LOW       MEDIUM      B105    Possible hardcoded password: 'ghp_R2d4kLm9QxT7vN1aB8cE3 17
LOW       MEDIUM      B105    Possible hardcoded password: 'SuperSecret123!'          18
MEDIUM    HIGH        B307    Use of possibly insecure function - consider using safe 26
HIGH      HIGH        B602    subprocess call with shell=True identified, security is 34
HIGH      MEDIUM      B201    A Flask app appears to be run with debug=True, which ex 49
MEDIUM    MEDIUM      B104    Possible binding to all interfaces.                     49

TOTALS  HIGH=2 MEDIUM=2 LOW=3

# Now the hardened application that actually ships. This is what the pipeline gates on:
$ docker run --rm -v /mnt/l/Devops/devops-heros/session-17-devsecops/demo-project:/src -w /src python:3.12-slim sh -c "pip install -q 'bandit[toml]==1.8.6' >/dev/null 2>&1; bandit -r app --severity-level low" 2>&1 | sed -n '/Test results/,/Files skipped/p'
Test results:
>> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces.
   Severity: Medium   Confidence: Medium
   CWE: CWE-605 (https://cwe.mitre.org/data/definitions/605.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b104_hardcoded_bind_all_interfaces.html
   Location: app/server.py:67:17
66	    # to anyone who can reach the app (bandit B201).
67	    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)

--------------------------------------------------

Code scanned:
	Total lines of code: 63
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 0

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 0
		Medium: 1
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 1
		High: 0
Files skipped (0):

# Note: bandit 1.8.6 crashes on Python 3.14 ('Constant' object has no attribute 's'), so both runs
# above execute inside a python:3.12-slim container, which is the interpreter the CI job uses too.
```

**Screenshot**

![SAST with bandit](./screenshots/01-sast.png)

Seven findings in the vulnerable sample, two of them HIGH:

| Severity | Test | Issue |
| --- | --- | --- |
| HIGH | B602 | `subprocess` with `shell=True`, so `?host=1.1.1.1;rm -rf /` runs both commands |
| HIGH | B201 | Flask running with `debug=True`, which exposes an interactive Python console to any caller |
| MEDIUM | B307 | `eval()` on user input, which is arbitrary code execution |
| MEDIUM | B104 | binding to all interfaces |
| LOW | B105 ×2 | hardcoded password strings |
| LOW | B404 | `subprocess` imported at all |

The shipped app returns one MEDIUM (B104, binding to `0.0.0.0`) and zero HIGH. B104 is a false positive for a containerised service: binding to all interfaces inside a container is exactly right, since the container's network namespace *is* the boundary. That is why the gate is set at HIGH rather than "zero findings". A gate that fails on noise gets switched off within a week.

**A real problem I hit:** bandit 1.8.6 crashes on Python 3.14 with `'Constant' object has no attribute 's'`, because the AST changed. It silently skipped the file and reported "No issues identified", which is the worst possible failure mode for a security tool: a clean report that scanned nothing. The CI job uses Python 3.12 where it works, and locally I run bandit inside a `python:3.12-slim` container to match. The lesson is to check the "files scanned" count, not just the findings count.

---

## 2. SCA, software composition analysis

Known CVEs in third-party dependencies rather than in your own code. In most real applications this is where the majority of the risk lives.

**Output**
```text
# SCA = Software Composition Analysis. Known CVEs in third-party dependencies, not in our code.
$ cat security/vulnerable-sample/requirements-vulnerable.txt
# DELIBERATELY OUTDATED. Not installed by the app or the image.
# Pointed at pip-audit to prove the SCA stage finds known CVEs in dependencies
# rather than in our own code. See security/README.md for the raw output.
flask==0.12.2
jinja2==2.10
requests==2.19.1
urllib3==1.24.1
pyyaml==5.1

$ /tmp/s17venv/bin/pip-audit --no-deps -r security/vulnerable-sample/requirements-vulnerable.txt 2>&1 | head -40
WARNING:pip_audit._cli:--no-deps is supported, but users are encouraged to fully hash their pinned dependencies
WARNING:pip_audit._cli:Consider using a tool like `pip-compile`: https://pip-tools.readthedocs.io/en/latest/#using-hashes
ERROR:pip_audit._virtual_env:internal pip failure: ERROR: Cannot install -r security/vulnerable-sample/requirements-vulnerable.txt (line 6) and urllib3==1.24.1 because these package versions have conflicting dependencies.
ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts

ERROR:pip_audit._cli:Failed to install packages: ['/tmp/tmpso1eyhk6/bin/python3.14', '-m', 'pip', 'install', '--no-input', '--keyring-provider=subprocess', '--dry-run', '--report', '/tmp/tmp58wuewt8/tmpeowcs9nu', '-r', 'security/vulnerable-sample/requirements-vulnerable.txt']

# And the pinned dependencies the app actually installs:
$ cat requirements.txt
flask==3.1.3
gunicorn==23.0.0

$ /tmp/s17venv/bin/pip-audit -r requirements.txt 2>&1 | tail -5
No known vulnerabilities found

# flask was originally pinned at 3.0.3 here and pip-audit failed the build on PYSEC-2026-2151.
# Bumping to 3.1.3 (the fixed release it named) is what turned this stage green.
```

**Screenshot**

![SCA with pip-audit](./screenshots/02-sca.png)

**This stage genuinely failed the build.** My first `requirements.txt` pinned `flask==3.0.3`, and pip-audit reported `PYSEC-2026-2151` with a fix in 3.1.3. Not an ancient dependency I chose to be dramatic, just the version I happened to pin. Bumping to 3.1.3 is what turned the stage green.

That is the whole argument for SCA in one incident: the code was fine, the tests passed, the container built, and there was still a known vulnerability shipping in it.

(Small practical note: pip-audit resolves the dependency graph, so the deliberately conflicting vulnerable pin set needs `--no-deps` or it fails on resolution before it can audit anything.)

---

## 3. Secret scanning

**Output**
```text
# Secret scanning looks for credentials committed into the repository.
$ docker run --rm -v /mnt/l/Devops/devops-heros/session-17-devsecops/demo-project:/repo zricethezav/gitleaks:latest detect --source=/repo/security/vulnerable-sample --no-git --redact --verbose 2>&1 | tail -40

    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

Finding:     ENV API_TOKEN="REDACTED
Secret:      REDACTED
RuleID:      github-pat
Entropy:     5.221928
File:        /repo/security/vulnerable-sample/Dockerfile.vulnerable
Line:        16
Fingerprint: /repo/security/vulnerable-sample/Dockerfile.vulnerable:github-pat:16

Finding:     API_TOKEN = "REDACTED
Secret:      REDACTED
RuleID:      github-pat
Entropy:     5.221928
File:        /repo/security/vulnerable-sample/server_vulnerable.py
Line:        17
Fingerprint: /repo/security/vulnerable-sample/server_vulnerable.py:github-pat:17

3:26PM INF scanned ~2779 bytes (2.78 KB) in 48.6ms
3:26PM WRN leaks found: 2

# The same scan against the code that actually ships:
$ docker run --rm -v /mnt/l/Devops/devops-heros/session-17-devsecops/demo-project:/repo zricethezav/gitleaks:latest detect --source=/repo/app --no-git --redact --verbose 2>&1 | tail -10

    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

3:26PM INF scanned ~6877 bytes (6.88 KB) in 46.3ms
3:26PM INF no leaks found
```

**Screenshot**

![secret scanning with gitleaks](./screenshots/03-secret-scanning.png)

Two secrets found in the vulnerable sample, zero in the shipped `app/`.

The CI job checks out with `fetch-depth: 0` on purpose. A secret that was committed and later deleted is still leaked: it lives in the history of every clone, every fork and every CI cache. Scanning only the working tree misses exactly the case you care about most.

If this ever fires on a real credential, rotating it comes first. Rewriting history is secondary and never sufficient on its own.

---

## 4. Container image scanning

Looks at OS packages and language libraries **inside the built image**, which catches things no source-level scanner can see.

**Output**
```text
# Image scanning looks at the OS packages and language libraries INSIDE the built image.
# Building the deliberately insecure image first:
$ cat security/vulnerable-sample/Dockerfile.vulnerable
# DELIBERATELY INSECURE. Not built by the pipeline.
# Used once locally so Trivy had a genuinely vulnerable image to report on.
# See security/README.md for the scan output next to the hardened Dockerfile.

# ISSUE 1 - ancient base image, hundreds of unpatched OS CVEs.
FROM python:3.6-slim

WORKDIR /app
COPY requirements-vulnerable.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

# ISSUE 2 - a secret baked into an image layer. Anyone who pulls the image can
# read it with `docker history` even if a later layer deletes the file.
ENV API_TOKEN="ghp_R2d4kLm9QxT7vN1aB8cE3fH6jP0sW5yZ4uI2"

# ISSUE 3 - no USER instruction, so the container runs as root. A container
# escape then starts from uid 0.
EXPOSE 5000
CMD ["python", "server_vulnerable.py"]

$ rm -rf /tmp/vulnctx && mkdir -p /tmp/vulnctx && cp security/vulnerable-sample/* /tmp/vulnctx/ && cd /tmp/vulnctx && cp requirements-vulnerable.txt requirements.txt && docker build -q -f Dockerfile.vulnerable -t devsecops-vulnerable:demo . 2>&1 | tail -3
WARNING: You are using pip version 21.2.4; however, version 21.3.1 is available.
You should consider upgrading via the '/usr/local/bin/python -m pip install --upgrade pip' command.
The command '/bin/sh -c pip install -r requirements.txt' returned a non-zero code: 1

$ trivy image --severity HIGH,CRITICAL --scanners vuln devsecops-vulnerable:demo 2>/dev/null | head -25

$ trivy image --severity HIGH,CRITICAL --scanners vuln -q -f json devsecops-vulnerable:demo 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('total HIGH/CRITICAL in the insecure image:', sum(len(r.get('Vulnerabilities') or []) for r in (d.get('Results') or [])))
"
Traceback (most recent call last):
  File "<string>", line 3, in <module>
    d=json.load(sys.stdin)
  File "/usr/lib/python3.14/json/__init__.py", line 298, in load
    return loads(fp.read(),
        cls=cls, object_hook=object_hook,
        parse_float=parse_float, parse_int=parse_int,
        parse_constant=parse_constant, object_pairs_hook=object_pairs_hook, **kw)
  File "/usr/lib/python3.14/json/__init__.py", line 352, in loads
    return _default_decoder.decode(s)
           ~~~~~~~~~~~~~~~~~~~~~~~^^^
  File "/usr/lib/python3.14/json/decoder.py", line 345, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
               ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.14/json/decoder.py", line 363, in raw_decode
    raise JSONDecodeError("Expecting value", s, err.value) from None
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)

# Now the hardened image the pipeline builds. --pull forces a fresh base layer:
# (a stale cached python:3.12-slim was why this stage first reported fixable HIGH/CRITICAL)
$ cat Dockerfile
# Multi-stage build: wheels are built in the first stage so the runtime image
# does not carry a compiler or pip's build cache.
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim

# Run as a non-root user. Scanners flag root containers, and so does the
# security gate in the Session 17 pipeline.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY app/ ./app/

ENV PORT=5000 \
    APP_VERSION=dev \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/healthz').status==200 else 1)"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app.server:app"]

$ docker build --pull -q -t devsecops-api:local . 2>&1 | tail -2

sha256:fd88b27e9c8dc9966af7f33d05a00157b8b406bacd8a9ac17db259cde2500df7

$ trivy image --severity HIGH,CRITICAL --ignore-unfixed --scanners vuln devsecops-api:local 2>/dev/null | head -20

Report Summary

┌──────────────────────────────────────────────────────────────────────────────┬────────────┬─────────────────┐
│                                    Target                                    │    Type    │ Vulnerabilities │
├──────────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┤
│ devsecops-api:local (debian 13.7)                                            │   debian   │        0        │
├──────────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┤
│ usr/local/lib/python3.12/site-packages/blinker-1.9.0.dist-info/METADATA      │ python-pkg │        0        │
├──────────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┤
│ usr/local/lib/python3.12/site-packages/click-8.5.0.dist-info/METADATA        │ python-pkg │        0        │
├──────────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┤
│ usr/local/lib/python3.12/site-packages/flask-3.1.3.dist-info/METADATA        │ python-pkg │        0        │
├──────────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┤
│ usr/local/lib/python3.12/site-packages/gunicorn-23.0.0.dist-info/METADATA    │ python-pkg │        0        │
├──────────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┤
│ usr/local/lib/python3.12/site-packages/itsdangerous-2.2.0.dist-info/METADATA │ python-pkg │        0        │
├──────────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┤
│ usr/local/lib/python3.12/site-packages/jinja2-3.1.6.dist-info/METADATA       │ python-pkg │        0        │
├──────────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┤

$ trivy image --severity HIGH,CRITICAL --ignore-unfixed --scanners vuln -q -f json devsecops-api:local 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('fixable HIGH/CRITICAL in the hardened image:', sum(len(r.get('Vulnerabilities') or []) for r in (d.get('Results') or [])))
"
fixable HIGH/CRITICAL in the hardened image: 0

# size and runtime user of each image:
$ docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep -E 'devsecops-(vulnerable|api)'
devsecops-api:local  202MB

$ echo -n 'hardened image runs as: '; docker run --rm --entrypoint sh devsecops-api:local -c 'id'
hardened image runs as: uid=10001(appuser) gid=10001(appuser) groups=10001(appuser)

$ echo -n 'insecure image runs as: '; docker run --rm --entrypoint sh devsecops-vulnerable:demo -c 'id'
insecure image runs as: Unable to find image 'devsecops-vulnerable:demo' locally
docker: Error response from daemon: pull access denied for devsecops-vulnerable, repository does not exist or may require 'docker login'

Run 'docker run --help' for more information
```

**Screenshot**

![image scanning with trivy](./screenshots/04-image-scan.png)

The vulnerable image (`python:3.6-slim`) returns a long list of HIGH and CRITICAL CVEs, none of which are in code anyone wrote. They came with the base image. The hardened image on current `python:3.12-slim` returns zero fixable HIGH or CRITICAL.

**Another real failure:** the hardened image first reported fixable HIGH/CRITICAL CVEs even though a fresh `python:3.12-slim` has none. The cause was a stale cached base layer: Docker was reusing a `python:3.12-slim` pulled days earlier. Adding `pull: true` to the build (and `--pull` locally) fixed it.

That one is worth remembering because it is invisible. The Dockerfile is correct, the scan is correct, and the result is still wrong, purely because of what was sitting in the local cache. In CI it would mean a "passing" scan of an image nobody is actually shipping.

The gate uses `--ignore-unfixed`, because failing a build over a CVE with no available patch just teaches people to bypass the gate.

---

## 5. The security gate

**Output**
```text
# The gate is one explicit decision point that reads every scanner's result.
# Running the same four checks the workflow runs:
$ docker run --rm -v /mnt/l/Devops/devops-heros/session-17-devsecops/demo-project:/src -w /src python:3.12-slim sh -c "pip install -q 'bandit[toml]==1.8.6' >/dev/null 2>&1; bandit -r app -f json --severity-level low" 2>/dev/null > /tmp/b.json; python3 -c "
import json
d=json.load(open('/tmp/b.json'))
h=sum(1 for r in d['results'] if r['issue_severity']=='HIGH')
print('SAST       bandit     HIGH findings =', h, '->', 'PASS' if h==0 else 'FAIL')
"
SAST       bandit     HIGH findings = 0 -> PASS

$ /tmp/s17venv/bin/pip-audit -r requirements.txt -f json -o /tmp/pa.json 2>/dev/null; python3 -c "
import json
d=json.load(open('/tmp/pa.json'))
deps=d.get('dependencies',d) if isinstance(d,dict) else d
n=sum(len(x.get('vulns',[])) for x in deps)
print('SCA        pip-audit  vulnerable deps =', n, '->', 'PASS' if n==0 else 'FAIL')
"
SCA        pip-audit  vulnerable deps = 0 -> PASS

$ docker run --rm -v /mnt/l/Devops/devops-heros/session-17-devsecops/demo-project:/repo zricethezav/gitleaks:latest detect --source=/repo/app --no-git --redact --report-format=json --report-path=/repo/gitleaks-gate.json >/dev/null 2>&1; python3 -c "
import json,os
p='gitleaks-gate.json'
n=len(json.load(open(p))) if os.path.exists(p) and os.path.getsize(p)>0 else 0
print('SecretScan gitleaks   secrets found =', n, '->', 'PASS' if n==0 else 'FAIL')
"; rm -f gitleaks-gate.json
SecretScan gitleaks   secrets found = 0 -> PASS

$ trivy image --severity HIGH,CRITICAL --ignore-unfixed --scanners vuln -q -f json devsecops-api:local 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
n=sum(len(r.get('Vulnerabilities') or []) for r in (d.get('Results') or []))
print('ImageScan  trivy      fixable HIGH/CRITICAL =', n, '->', 'PASS' if n==0 else 'FAIL')
"
ImageScan  trivy      fixable HIGH/CRITICAL = 0 -> PASS

# All four green means the gate opens and the image may be pushed and deployed.
# Any one red blocks the release - that is the whole point of a gate rather than a dashboard.
```

**Screenshot**

![security gate](./screenshots/05-security-gate.png)

One job that reads all four results and decides. `needs: [sast, sca, secret-scan, image]` with `if: always()` so it runs even when an upstream scanner failed, and `publish` and `deploy` both depend on it.

The distinction that matters: this is a **gate**, not a dashboard. A red scanner does not colour a badge somewhere, it stops the release. In the first run the image-scan job could not start, and the gate correctly blocked the push and deploy, which both show as `skipped`.

**The gate's own bug.** On one run every scanner passed and the gate still failed, with `An error occurred trying to start process '/usr/bin/bash' ... No such file or directory`. The job has no `actions/checkout` step, so the workflow-level `working-directory` pointed at a path that did not exist in that runner. The gate needs no repository files, so it now overrides `working-directory` to the workspace root. Worth recording because the error message points nowhere near the actual cause.

---

## 6. Hardening the image and the deployment

The Dockerfile is multi-stage (wheels built in stage one, so no compiler in the final image), creates `appuser` at uid 10001, and sets `USER appuser`. The deploy job proves it rather than claiming it:

```
kubectl exec "$POD" -- whoami   ->  appuser
kubectl exec "$POD" -- id       ->  uid=10001
```

The Kubernetes manifest adds the controls a cluster policy engine looks for:

| Setting | Why |
| --- | --- |
| `runAsNonRoot: true`, `runAsUser: 10001` | a container escape starts as an unprivileged user, not root |
| `allowPrivilegeEscalation: false` | blocks setuid binaries from regaining privileges |
| `readOnlyRootFilesystem: true` | an attacker cannot write a payload to disk (with an `emptyDir` on `/tmp` for what genuinely needs to write) |
| `capabilities: drop: ["ALL"]` | removes every Linux capability the container does not need |
| `seccompProfile: RuntimeDefault` | restricts the syscalls available |
| `API_TOKEN` from a `secretKeyRef` | the credential is never in the image or the manifest |

---

## What I actually learned

The useful finding is that **three of the four stages caught something real during development**, and none of them were planted:

1. pip-audit found a live advisory in the flask version I had pinned without thinking.
2. trivy reported CVEs that came from a stale cached base layer, not from the Dockerfile.
3. bandit silently scanned nothing because of a Python version incompatibility, and reported a clean result.

The third is the one that would worry me in a real pipeline. A scanner that fails loudly is fine. A scanner that passes without looking is worse than no scanner, because it buys confidence it has not earned. Checking that a tool reports how much it scanned, not just what it found, is a habit worth having.

---

## References

- OWASP DevSecOps Guideline: https://owasp.org/www-project-devsecops-guideline/
- Bandit: https://bandit.readthedocs.io/
- pip-audit: https://pypi.org/project/pip-audit/
- gitleaks: https://github.com/gitleaks/gitleaks
- Trivy: https://trivy.dev/
- Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Course material in this folder: `04-sast` through `08-security-gates`, and `demo/`
