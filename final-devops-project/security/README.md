# Security (DevSecOps)

Security here is not a separate phase at the end. Every check below runs in the pipeline on every push, and a red one stops the release: nothing gets pushed to the registry or deployed unless the **security gate** job is green. I ran each scanner locally too, with the same versions, so the numbers on this page are real output, not what the tools are supposed to print.

| Layer | Tool | What it looks at | Gate | Result |
| --- | --- | --- | --- | --- |
| SAST | bandit 1.8.6 | backend Python source | any finding fails | 0 issues in 378 lines |
| SCA (Python) | pip-audit 2.9.0 | pinned `requirements.txt` | any known CVE fails | no known vulnerabilities |
| SCA (npm) | npm audit | `package-lock.json` | high or critical fails | 0 vulnerabilities |
| Secrets | gitleaks v8.30.1 | working tree **and** every commit that touched the project | any leak fails | no leaks, 14 commits |
| Images | trivy 0.75 | OS packages and libraries inside both images | fixable HIGH/CRITICAL fails | both pass (details below) |
| IaC | trivy config | Helm chart, Dockerfiles, manifests, Terraform | HIGH/CRITICAL fails | 0 HIGH/CRITICAL |
| Runtime | Pod Security "restricted" | every pod in the `kharcha` namespace | admission refuses | root pods rejected |

Files in this folder:

- [`bandit.yaml`](./bandit.yaml): skips only the tests folder (asserts are on purpose there). No rule is switched off globally. A false positive would get an inline `# nosec <ID>` with a reason next to it.
- [`gitleaks.toml`](./gitleaks.toml): the default ruleset plus a three-item allowlist: the npm lock file (full of integrity hashes that look like keys), the screenshots folder, and the local-only Compose fallback password `kharcha_local_dev_only`.

## The finding that blocked my own release

The first time I scanned the frontend image, Trivy found **43 fixable HIGH CVEs**. None of them were in my code. They all came from the Alpine packages inside the `nginxinc/nginx-unprivileged:1.29-alpine` base image:

```text
ghcr.io/lavya255/kharcha-frontend:0927fed (alpine 3.23.4)
Total: 43 (HIGH: 43, CRITICAL: 0)
  by package: {'curl': 10, 'libcurl': 10, 'libexpat': 6, 'libuuid': 6, 'pcre2': 4,
               'libcrypto3': 2, 'libssl3': 2, 'c-ares': 1, 'libxml2': 1, 'tiff': 1}
gate exit=1  (1 = blocked)
```

Two changes in the frontend Dockerfile fixed it:

1. `apk upgrade --no-cache` pulls in the patched versions of everything that has a fix.
2. `apk del curl`. Nothing in the image uses curl (the healthcheck is busybox `wget`), so 20 of the 43 findings were in a tool that only adds attack surface. Removing it beats patching it.

After, scanning the image CI actually pushed to GHCR:

```text
kharcha-frontend:0927fed: {'HIGH': 43, 'LOW': 50, 'MEDIUM': 81, 'UNKNOWN': 2}  fixable: 176
kharcha-frontend:a5e2e0d: none  fixable: 0
kharcha-backend:a5e2e0d:  {'HIGH': 44, 'LOW': 61, 'MEDIUM': 58, 'UNKNOWN': 3}  fixable: 2
```

The frontend went from 176 vulnerabilities to **zero at any severity**. The price is a 21 MB layer, because the upgraded packages sit on top of the old ones in the base layer. The real long-term fix is a newer base image once upstream publishes one; until then this is the honest trade.

### Five days later, a new CVE, and a cache that froze the patch

On Oct 21 the gate blocked the frontend again: one HIGH, `libexpat` CVE-2026-77214, published after my last green build, with a fixed version (2.9.0-r0) already in Alpine's repository. My Dockerfile runs `apk upgrade` precisely to pick up fixes like that, so why didn't it? The CI log said `RUN apk upgrade ... CACHED`. The build had reused the layer from Oct 16, so the upgrade never ran again and the image kept the old library.

The fix: the runtime stage is named (`AS runtime`) and the pipeline builds it with `no-cache-filters: runtime`, so `apk upgrade` runs fresh every time while the slow npm build stage stays cached. A fresh build has `libexpat-2.9.0-r0` and passes the gate. Lesson: a layer cache is a snapshot of the internet on the day it was made, and a security patch step must never come from one.

### Why the backend passes with 44 HIGHs

The backend is on `python:3.12-slim` (Debian 13). Its 44 HIGH findings are all in Debian packages with **no fixed version available yet**, which is what `--ignore-unfixed` in the gate means: fail on what I can act on today, report everything else. The full report (every severity, fixed or not) is uploaded as a build artifact on every run, so nothing is hidden, it just does not block. The 2 fixable findings are LOW/MEDIUM.

## Secret scanning that actually works

A scanner that always says "no leaks" proves nothing, so I planted a fake AWS key pair in a scratch folder (never in the repo) and scanned it:

```text
Finding:     aws_access_key_id = REDACTED
RuleID:      aws-access-token
Finding:     aws_secret_access_key = REDACTED
RuleID:      generic-api-key
WRN leaks found: 2
exit=1
```

Two findings, exit code 1, and the values are redacted in the output (so the scan log does not become the leak). The pipeline scans with `fetch-depth: 0`, because a secret that was committed and then deleted is still in the history and still leaked.

## How secrets are handled

- **No password exists in git.** The database password is generated inside the cluster by [`kubernetes/create-db-secret.sh`](../kubernetes/create-db-secret.sh) (`openssl rand -hex 24`), only if the Secret does not exist yet, and is never printed. The chart only references the Secret by name (`database.existingSecret`).
- **DATABASE_URL is assembled at runtime** from the Secret with Kubernetes `$(VAR)` expansion, so the full connection string never exists in a ConfigMap, a values file or a manifest.
- **CI uses short-lived tokens only.** Pushing to GHCR and pulling inside the kind cluster both use the run's own `GITHUB_TOKEN`, which expires when the job ends. The repo has no long-lived registry or cloud credentials stored at all.
- **Terraform state is git-ignored** (it contains every resource attribute in plain text), as are `terraform.tfvars` and `.env`.
- If a Secret does get re-created, [`troubleshooting/sync-db-password.sh`](../troubleshooting/sync-db-password.sh) fixes the mismatch by passing the password through stdin, so it never appears in output or in a process list.

## Container and pod hardening

Every container in the app passes the Kubernetes **restricted** Pod Security Standard, which the namespace enforces (a pod asking for root is refused at admission, see `screenshots/terminal/05-k8s-namespace-secret-pss.png`):

| | backend | frontend | postgres |
| --- | --- | --- | --- |
| user | 10001 | 101 | 70 |
| read-only root filesystem | yes | yes | yes |
| capabilities | all dropped | all dropped | all dropped |
| privilege escalation | no | no | no |
| seccomp | RuntimeDefault | RuntimeDefault | RuntimeDefault |
| service account token | not mounted | not mounted | not mounted |

Proved on the live pods, not just in YAML:

```text
$ kubectl exec -n kharcha deploy/kharcha-backend -c api -- sh -c 'touch /app/hacked'
touch: cannot touch '/app/hacked': Read-only file system
```

## What I accepted, and why

`trivy config` finds no HIGH or CRITICAL issue. These are the LOW/MEDIUM ones it does report, each looked at:

| Check | Where | Why it stays |
| --- | --- | --- |
| KSV-0125 trusted registries | deployments | The images come from my own GHCR namespace. The check wants an allow-list policy (e.g. Kyverno), which is the next step, not a chart change. |
| KSV-01010 sensitive ConfigMap | configmap.yaml | False positive: the keys are named `DB_HOST`, `DB_USER`. The values are a hostname and a username; the password is in a Secret. |
| KSV-0020/0021 UID/GID <= 10000 | frontend, postgres | 101 and 70 are the users the official nginx-unprivileged and postgres images are built for. Changing them breaks file ownership inside those images. Non-root is what matters, and it is enforced. |
| KSV-0110 default namespace | templates | Static scan of a template with no namespace. Helm and ArgoCD always install into `kharcha`. |
| KSV-0039/0040 limit range / quota | manifests | Reported on the files that ARE the LimitRange and ResourceQuota, and on the ArgoCD Application. Not applicable. |
| AWS-0017 log group CMK | terraform | Flow logs and EKS control-plane logs use CloudWatch's default encryption. A customer-managed KMS key per log group costs money and adds key-policy work for logs that hold no secrets. EKS Secrets themselves DO use a customer-managed key. |

## Reproduce it

```bash
# from final-devops-project/
docker run --rm -v "$PWD:/src" -w /src python:3.12-slim sh -c 'pip install -q bandit==1.8.6 && bandit -c security/bandit.yaml -r application/backend/app'
docker run --rm -v "$PWD:/src" -w /src python:3.12-slim sh -c 'pip install -q pip-audit==2.9.0 && pip-audit -r application/backend/requirements.txt'
docker run --rm -v "$PWD/..:/repo" zricethezav/gitleaks:v8.30.1 dir /repo/final-devops-project --config /repo/final-devops-project/security/gitleaks.toml --redact
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed ghcr.io/lavya255/kharcha-frontend:<tag>
trivy config --severity HIGH,CRITICAL .
```

Captured runs: `screenshots/terminal/12-sast-bandit.png` to `16-config-scan-trivy.png`.
