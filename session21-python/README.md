# Session 21: Final DevOps Project

**Author:** Lavya ([@LAVYA255](https://github.com/LAVYA255))
**Course:** SST DevOps & Cloud [SWE]
**Session:** 21 - Final Project
**Repository:** `devops-heros / session21-python`

The TaskBoard project already ships in this folder: FastAPI backend, React frontend, Postgres, Alembic migrations, a Helm chart and a CI/CD workflow. This writeup covers running it and showing the application working. `GRADING.md` is the course's own file and is untouched.

Run on Docker 29.1.3 in WSL2 Ubuntu.

---

## The application

![TaskBoard dashboard](./screenshots/01-taskboard-ui.jpg)

![TaskBoard API docs](./screenshots/02-taskboard-api-docs.jpg)

Three services behind Docker Compose:

| Service | Image | Role |
| --- | --- | --- |
| `postgres` | `postgres:16-alpine` | Database, with a named volume so data survives restarts |
| `backend` | built from `backend/` | FastAPI, runs `alembic upgrade head` on startup then serves on 8000 |
| `frontend` | built from `frontend/` | React built with Vite, served by nginx, which also proxies `/api/` to the backend |

The tasks visible in the dashboard were created through the API during this run, not seeded.

---

## Bringing it up

**Commands**
```bash
ls -1
cat docker-compose.yml
cat /tmp/tb-override.yml
docker compose -f docker-compose.yml -f /tmp/tb-override.yml down -v 2>&1 | tail -4
docker compose -f docker-compose.yml -f /tmp/tb-override.yml up -d --build 2>&1 | tail -10
docker compose -f docker-compose.yml -f /tmp/tb-override.yml ps
docker compose -f docker-compose.yml -f /tmp/tb-override.yml logs backend 2>&1 | grep -iE 'running upgrade|Uvicorn running|Application startup' | head -6
```

**Output**
```text
# The Session 21 project (TaskBoard) already exists in the repo: FastAPI backend,
# React frontend, Postgres, a Helm chart and a CI/CD workflow. The job here is to
# run it and show the application itself.
$ ls -1
GRADING.md
README.md
backend
docker-compose.yml
frontend
helm
k8s
monitoring
scripts
terraform
troubleshooting

$ cat docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: taskboard
      POSTGRES_USER: taskboard
      POSTGRES_PASSWORD: taskboard
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+psycopg://taskboard:taskboard@postgres:5432/taskboard
    depends_on:
      - postgres
    ports:
      - "8000:8000"

  frontend:
    build: ./frontend
    depends_on:
      - backend
    ports:
      - "3000:80"

volumes:
  postgres-data:

# Three local adjustments, all in an override file so the committed compose file stays untouched.
#
# 1. Ports 3000 and 5432 are already taken on this machine by the Session 20 Grafana
#    and an earlier Postgres, so the override remaps them. Note the '!override' tag:
#    Compose MERGES list fields across files, so without it the frontend tries to bind
#    BOTH 3000 and 3100 and fails with 'Bind for 0.0.0.0:3000 failed: port is already
#    allocated'. !override replaces the list. (!reset, which I reached for first,
#    empties it instead, which left the containers up with no published ports at all.)
#
# 2. The backend runs 'alembic upgrade head' on startup and died the first time with
#    'connection to server at 172.24.0.2, port 5432 failed: Connection refused'.
#    Plain depends_on only waits for the container to be CREATED, not for Postgres to
#    accept connections, so the override adds a healthcheck and waits on service_healthy.
#
# 3. The frontend's nginx resolves its proxy_pass upstream once at startup and exits with
#    'host not found in upstream "backend"' if the backend is not up yet, so it waits too.
$ cat /tmp/tb-override.yml
services:
  postgres:
    ports: !reset []
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taskboard -d taskboard"]
      interval: 3s
      timeout: 3s
      retries: 20

  backend:
    ports: !override ["8100:8000"]
    depends_on:
      postgres:
        condition: service_healthy

  frontend:
    ports: !override ["3100:80"]
    depends_on:
      backend:
        condition: service_started

$ docker compose -f docker-compose.yml -f /tmp/tb-override.yml down -v 2>&1 | tail -4
 Volume session21-python_postgres-data  Removing
 Network session21-python_default  Removing
 Volume session21-python_postgres-data  Removed
 Network session21-python_default  Removed

$ docker compose -f docker-compose.yml -f /tmp/tb-override.yml up -d --build 2>&1 | tail -10
 Container session21-python-frontend-1  Creating
 Container session21-python-frontend-1  Created
 Container session21-python-postgres-1  Starting
 Container session21-python-postgres-1  Started
 Container session21-python-postgres-1  Waiting
 Container session21-python-postgres-1  Healthy
 Container session21-python-backend-1  Starting
 Container session21-python-backend-1  Started
 Container session21-python-frontend-1  Starting
 Container session21-python-frontend-1  Started

$ docker compose -f docker-compose.yml -f /tmp/tb-override.yml ps
NAME                          IMAGE                       COMMAND                  SERVICE    CREATED          STATUS                    PORTS
session21-python-backend-1    session21-python-backend    "sh -c 'alembic upgr…"   backend    25 seconds ago   Up 20 seconds             0.0.0.0:8100->8000/tcp, [::]:8100->8000/tcp
session21-python-frontend-1   session21-python-frontend   "/docker-entrypoint.…"   frontend   25 seconds ago   Up 20 seconds             0.0.0.0:3100->80/tcp, [::]:3100->80/tcp
session21-python-postgres-1   postgres:16-alpine          "docker-entrypoint.s…"   postgres   25 seconds ago   Up 24 seconds (healthy)   5432/tcp

# the migration now runs after Postgres is ready:
$ docker compose -f docker-compose.yml -f /tmp/tb-override.yml logs backend 2>&1 | grep -iE 'running upgrade|Uvicorn running|Application startup' | head -6
backend-1  | INFO  [alembic.runtime.migration] Running upgrade  -> 0001_create_tasks
backend-1  | INFO:     Waiting for application startup.
backend-1  | INFO:     Application startup complete.
backend-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## Verifying it

**Output**
```text
# Backend:
$ curl -s http://localhost:8100/health; echo
{"status":"UP"}

$ curl -s http://localhost:8100/ready; echo
{"status":"READY"}

$ curl -s -o /dev/null -w 'OpenAPI docs -> HTTP %{http_code}\n' http://localhost:8100/docs
OpenAPI docs -> HTTP 200

$ curl -s http://localhost:8100/api/tasks; echo
[]

# Creating tasks through the API so the UI has something to show:
$ curl -s -X POST http://localhost:8100/api/tasks -H 'Content-Type: application/json' -d '{"title":"Finish the Session 20 GitOps writeup","priority":"HIGH","assignee":"Lavya"}'; echo
{"title":"Finish the Session 20 GitOps writeup","description":"","priority":"HIGH","status":"TODO","assignee":"Lavya","id":1,"created_at":"2026-10-07T16:41:13.768203Z"}

$ curl -s -X POST http://localhost:8100/api/tasks -H 'Content-Type: application/json' -d '{"title":"Review the DevSecOps security gate","priority":"HIGH","assignee":"Lavya"}'; echo
{"title":"Review the DevSecOps security gate","description":"","priority":"HIGH","status":"TODO","assignee":"Lavya","id":2,"created_at":"2026-10-07T16:41:13.794527Z"}

$ curl -s -X POST http://localhost:8100/api/tasks -H 'Content-Type: application/json' -d '{"title":"Submit the Season 3 Google Form","assignee":"Lavya"}'; echo
{"title":"Submit the Season 3 Google Form","description":"","priority":"MEDIUM","status":"TODO","assignee":"Lavya","id":3,"created_at":"2026-10-07T16:41:13.817207Z"}

$ curl -s -X POST http://localhost:8100/api/tasks -H 'Content-Type: application/json' -d '{"title":"Tear down the LocalStack containers","priority":"LOW"}'; echo
{"title":"Tear down the LocalStack containers","description":"","priority":"LOW","status":"TODO","assignee":"Unassigned","id":4,"created_at":"2026-10-07T16:41:13.838913Z"}

# Updating one through PUT (the API has no PATCH, and the model uses status rather than a done flag):
$ curl -s -X PUT http://localhost:8100/api/tasks/1 -H 'Content-Type: application/json' -d '{"title":"Finish the Session 20 GitOps writeup","status":"DONE","priority":"HIGH","assignee":"Lavya"}'; echo
{"title":"Finish the Session 20 GitOps writeup","description":"","priority":"HIGH","status":"DONE","assignee":"Lavya","id":1,"created_at":"2026-10-07T16:41:13.768203Z"}

$ curl -s -X PUT http://localhost:8100/api/tasks/2 -H 'Content-Type: application/json' -d '{"title":"Review the DevSecOps security gate","status":"IN_PROGRESS","priority":"HIGH","assignee":"Lavya"}'; echo
{"title":"Review the DevSecOps security gate","description":"","priority":"HIGH","status":"IN_PROGRESS","assignee":"Lavya","id":2,"created_at":"2026-10-07T16:41:13.794527Z"}

$ curl -s http://localhost:8100/api/tasks | python3 -m json.tool
[
    {
        "title": "Tear down the LocalStack containers",
        "description": "",
        "priority": "LOW",
        "status": "TODO",
        "assignee": "Unassigned",
        "id": 4,
        "created_at": "2026-10-07T16:41:13.838913Z"
    },
    {
        "title": "Submit the Season 3 Google Form",
        "description": "",
        "priority": "MEDIUM",
        "status": "TODO",
        "assignee": "Lavya",
        "id": 3,
        "created_at": "2026-10-07T16:41:13.817207Z"
    },
    {
        "title": "Review the DevSecOps security gate",
        "description": "",
        "priority": "HIGH",
        "status": "IN_PROGRESS",
        "assignee": "Lavya",
        "id": 2,
        "created_at": "2026-10-07T16:41:13.794527Z"
    },
    {
        "title": "Finish the Session 20 GitOps writeup",
        "description": "",
        "priority": "HIGH",
        "status": "DONE",
        "assignee": "Lavya",
        "id": 1,
        "created_at": "2026-10-07T16:41:13.768203Z"
    }
]

$ curl -s http://localhost:8100/api/tasks/stats; echo
{"total":4,"todo":2,"inProgress":1,"done":1}

# Frontend:
$ curl -s -o /dev/null -w 'frontend -> HTTP %{http_code}\n' http://localhost:3100/
frontend -> HTTP 200

$ curl -s http://localhost:3100/ | head -3
<!doctype html><html><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/><title>TaskBoard</title>  <script type="module" crossorigin src="/assets/index-BhFpkPY_.js"></script>
  <link rel="stylesheet" crossorigin href="/assets/index-DkMuKOF6.css">
</head><body><div id="root"></div></body></html>

# and the API through the frontend's own nginx proxy, which is how the SPA calls it:
$ curl -s -o /dev/null -w 'GET /api/tasks via proxy -> HTTP %{http_code}\n' http://localhost:3100/api/tasks
GET /api/tasks via proxy -> HTTP 200

$ curl -s http://localhost:3100/api/tasks | python3 -c "
import json,sys
for t in json.load(sys.stdin):
    print('  #%s  %-12s %-8s %-10s %s' % (t['id'], t['status'], t['priority'], t['assignee'], t['title']))
"
  #4  TODO         LOW      Unassigned Tear down the LocalStack containers
  #3  TODO         MEDIUM   Lavya      Submit the Season 3 Google Form
  #2  IN_PROGRESS  HIGH     Lavya      Review the DevSecOps security gate
  #1  DONE         HIGH     Lavya      Finish the Session 20 GitOps writeup

# Database, queried directly to prove the data really persisted:
$ docker compose -f docker-compose.yml -f /tmp/tb-override.yml exec -T postgres psql -U taskboard -d taskboard -c 'select id, title, status, priority, assignee from tasks order by id;'
 id |                title                 |   status    | priority |  assignee
----+--------------------------------------+-------------+----------+------------
  1 | Finish the Session 20 GitOps writeup | DONE        | HIGH     | Lavya
  2 | Review the DevSecOps security gate   | IN_PROGRESS | HIGH     | Lavya
  3 | Submit the Season 3 Google Form      | TODO        | MEDIUM   | Lavya
  4 | Tear down the LocalStack containers  | TODO        | LOW      | Unassigned
(4 rows)

$ docker compose -f docker-compose.yml -f /tmp/tb-override.yml exec -T postgres psql -U taskboard -d taskboard -c '\dt'
              List of relations
 Schema |      Name       | Type  |   Owner
--------+-----------------+-------+-----------
 public | alembic_version | table | taskboard
 public | tasks           | table | taskboard
(2 rows)

$ echo 'UI: http://localhost:3100   API docs: http://localhost:8100/docs'
UI: http://localhost:3100   API docs: http://localhost:8100/docs
```

What the run shows, end to end:

- `/health` returns `{"status":"UP"}` and `/ready` returns `{"status":"READY"}`, which are the two separate probes the Helm chart wires to liveness and readiness. Exactly the distinction from Session 13: UP means the process is alive, READY means it can actually serve, which here includes reaching the database.
- Swagger UI at `/docs` returns 200 and lists every route.
- Four tasks created with POST, two updated with PUT, and `/api/tasks/stats` reflects the changes.
- The frontend returns 200 and serves the built Vite bundle.
- `GET /api/tasks` **through the frontend's nginx proxy** returns 200, which is what the SPA itself does.
- A direct `psql` query against Postgres shows the rows really persisted, with the right status, priority and assignee.

That last check matters. The API returning JSON only proves the API works. Querying the database directly proves the data actually landed.

---

## Three things that broke, and why

Running someone else's compose stack on a machine that already has a lot running turned out to be the interesting part.

### 1. The backend died before Postgres was ready

```
sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed:
connection to server at "172.24.0.2", port 5432 failed: Connection refused
```

The backend's command is `alembic upgrade head && uvicorn ...`. It ran the migration immediately, Postgres had not finished starting, and the container exited 1.

`depends_on: [postgres]` on its own only waits for the container to be **created**, not for the database to accept connections. The fix is a healthcheck plus a condition:

```yaml
postgres:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U taskboard -d taskboard"]
    interval: 3s
    retries: 20
backend:
  depends_on:
    postgres:
      condition: service_healthy
```

This is the compose equivalent of the readiness probe idea from Session 13: "running" and "ready to serve" are different states, and depending on the wrong one causes exactly this class of startup race.

### 2. nginx exited because it could not resolve `backend`

```
nginx: [emerg] host not found in upstream "backend" in /etc/nginx/conf.d/default.conf:13
```

nginx resolves `proxy_pass` upstreams **once, at startup**, and exits hard if the name does not resolve. The backend was still running its migration at that point, so the name was not there yet. Same fix: make the frontend wait on the backend too.

Worth knowing generally, because it is a common surprise: nginx will not retry DNS for a statically configured upstream. If the upstream can come and go, you need a `resolver` directive and a variable in `proxy_pass`.

### 3. Compose merges port lists instead of replacing them

The messy one. Ports 3000 and 5432 were already taken on this machine (Grafana from Session 20, and an earlier Postgres), so I put remapped ports in an override file. The frontend still failed:

```
Bind for 0.0.0.0:3000 failed: port is already allocated
```

Compose **merges** list fields across files rather than overriding them, so the frontend was trying to bind both `3000:80` from the base file and `3100:80` from mine.

I reached for `!reset` first, which was wrong in an instructive way: it empties the list. The containers then started cleanly with **no published ports at all**, which looks like success in `docker compose ps` until you try to curl anything. The correct tag is `!override`:

```yaml
frontend:
  ports: !override ["3100:80"]   # replaces the list
postgres:
  ports: !reset []               # removes it entirely
```

All three fixes live in an override file, so the committed `docker-compose.yml` is unchanged.

---

## How this project ties the course together

| Session | Where it shows up here |
| --- | --- |
| 6, 7 Docker | Multi-stage builds; the frontend compiles with Node and ships on nginx |
| 8 Networking and volumes | Compose network for service discovery by name; named volume for Postgres |
| 10 Core objects | The Helm chart's Deployments, Services and rollout strategy |
| 12 ConfigMaps and Secrets | `DATABASE_URL` injected as config, credentials from a Secret |
| 13 Probes | `/health` and `/ready` as liveness and readiness |
| 15 Helm | `helm/taskboard/` packages the whole thing |
| 16, 17 CI/CD | `.github/workflows/ci-cd.yml` builds, tests and pushes the images |

---

## References

- Project source: [`session21-python/`](.)
- Compose merge and override: https://docs.docker.com/reference/compose-file/merge/
- Compose healthcheck conditions: https://docs.docker.com/reference/compose-file/services/#depends_on
- FastAPI: https://fastapi.tiangolo.com/
- Alembic: https://alembic.sqlalchemy.org/
