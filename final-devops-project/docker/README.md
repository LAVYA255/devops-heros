# Docker

The Dockerfiles live next to the code they build ([`application/backend/Dockerfile`](../application/backend/Dockerfile), [`application/frontend/Dockerfile`](../application/frontend/Dockerfile)) so each build context is just that service. The full local stack is [`docker-compose.yml`](../docker-compose.yml) at the project root. This folder holds the development override and this write-up.

```bash
# from final-devops-project/
docker compose up --build           # http://localhost:3000 (UI), :8000 (API)
docker compose -f docker-compose.yml -f docker/compose.dev.yml up --build   # backend hot reload
```

## The images

| | backend | frontend |
| --- | --- | --- |
| base | `python:3.12-slim` | `node:22-alpine` (build) then `nginxinc/nginx-unprivileged:1.29-alpine` |
| stages | builder (wheels) then runtime | build (Vite) then nginx |
| user | `kharcha`, uid 10001 | `nginx`, uid 101 |
| port | 8000 | 8080 (unprivileged, no root needed to bind) |
| size | 347 MB | 112 MB |
| healthcheck | `/health` | `/healthz` (busybox wget) |
| Trivy, fixable HIGH/CRITICAL | 0 | 0 (0 vulnerabilities at all) |

What each choice is for:

- **Multi-stage builds.** The backend compiles wheels in a builder stage and only copies the finished wheels across, then uninstalls pip from the runtime image. The frontend's whole Node toolchain stays in the build stage: the final image has no `node_modules`, no Node, and zero layers mentioning npm (checked with `docker history`, see `screenshots/terminal/04-nonroot-images.png`).
- **Dependency layers first.** `requirements.txt` and `package*.json` are copied and installed before the source, so editing code reuses the cached dependency layer and rebuilds in seconds.
- **Non-root, always.** Both images end with a numeric `USER`, which is what the Kubernetes `runAsNonRoot` check needs to verify it without guessing.
- **Patched, smaller attack surface.** The frontend runs `apk upgrade` and removes curl. That took it from 43 fixable HIGH CVEs to none at all (story in [`security/README.md`](../security/README.md)). It also made the image 30 MB bigger (82 MB to 112 MB), because the upgraded packages are a new layer on top of the base. I took the trade.
- **nginx sized for a container.** The stock `worker_processes auto` means one worker per CPU **on the node**. On my 24-core laptop a frontend pod limited to 0.2 CPU was running 24 workers. It is pinned to 2 in the image (the root filesystem is read-only in Kubernetes, so nothing can rewrite `nginx.conf` at startup).
- **Same-origin API.** The browser only talks to nginx, which proxies `/api` to the backend. No CORS, and the backend is never exposed to the browser directly. The upstream comes from `BACKEND_UPSTREAM`, rendered by the nginx image's envsubst step, and is resolved per request with the container's own resolver, so nginx does not crash at startup when the backend is not up yet.
- **Line endings.** `entrypoint.sh` is run through `sed 's/\r$//'` in the build, and `.gitattributes` forces LF. A Windows checkout with CRLF otherwise gives the famous `/bin/sh^M: not found`.

## Compose details that matter

- `depends_on: condition: service_healthy` everywhere: the backend waits for `pg_isready`, the frontend waits for the backend's healthcheck. Plain `depends_on` only waits for the container to *exist*.
- The database password is `${POSTGRES_PASSWORD:-kharcha_local_dev_only}`, so a fresh clone works with no setup, and `.env` (git-ignored, template in `.env.example`) overrides it.
- One backend container, so it migrates itself on start (`RUN_MIGRATIONS=true`). In Kubernetes several pods start at once, so there an init container runs the migration under a Postgres advisory lock instead.

## The dev override, tested

[`compose.dev.yml`](./compose.dev.yml) mounts `application/backend/app` read-only over the copy in the image and runs uvicorn with `--reload`. The production image is untouched. Real run (`screenshots/terminal/33-compose-dev-override.png`):

```text
$ curl -s localhost:8000/health
{"status":"UP","version":"dev-reload"}

$ touch application/backend/app/config.py
WARNING:  WatchFiles detected changes in 'app/config.py'. Reloading...
INFO:     Application startup complete.

$ docker compose ... exec -T backend sh -c 'touch /app/app/x'
touch: cannot touch '/app/app/x': Read-only file system
```

One gotcha I hit writing it: with several `-f` files, Compose resolves relative paths from the directory of the **first** file. My first version used `../application/...` (relative to `docker/`), which would have mounted a folder that does not exist.

## Bugs the containers caught

| Symptom | Cause | Fix |
| --- | --- | --- |
| Backend crash-looped in Compose with `ModuleNotFoundError: No module named 'app'` while all unit tests passed | `alembic.ini` had no `prepend_sys_path = .`, so Alembic could not import the models. The tests build the schema with `create_all()` and never run a migration. | Added the setting, plus a CI job that runs real migrations on Postgres. |
| `COPY --chmod` failed on the classic builder | `--chmod` needs BuildKit | A plain `RUN chmod` |
| Security headers vanished on some responses | nginx `add_header` in a `location` silently drops every `add_header` from the server block | Headers in a snippet, included in each location |
