# Troubleshooting

Two kinds of problems are written up here:

1. **Faults I injected on purpose** into a separate copy of the app (namespace `kharcha-lab`, installed with the helm CLI). It has to be separate: the real `kharcha` namespace is owned by ArgoCD with self-heal on, which reverts a hand edit in about two seconds (shown at the end), so I could never break it for long enough to debug.
2. **Real incidents** that happened while I built this, including two that the injected faults uncovered by accident. Those were the most useful part of the whole project.

Every scenario follows the same steps: **identify** (what does the user or the operator see), **investigate** (which command narrows it down), **root cause**, **fix**, **verify**, and **prevention**. All output below is copied from real runs; each has a rendered capture in `screenshots/terminal/`.

The lab has a small curl pod (`probe`) inside the namespace, so every check goes through the same path a user request takes: frontend nginx, backend Service, backend pod, Postgres.

| # | Scenario | Type | What it looks like | Root cause |
| --- | --- | --- | --- | --- |
| 1 | Typo in DB host | injected | new pods stuck in `Init`, app still fine | DNS name does not exist |
| 1b | Same typo, first attempt | **real bug found** | nothing looks wrong at all | chart created a second, empty database |
| 2 | Image tag never pushed | injected | `ImagePullBackOff` | tag not in GHCR |
| 3 | DB Secret re-created | injected | new pods stuck in `Init` | password mismatch with Postgres |
| 4 | Service targetPort edited | injected | 502 on every API call, all pods Ready | Service points at the wrong port |
| 5 | Wrong scrape annotation | injected | Prometheus targets DOWN, app fine | annotation points at the wrong port |
| 6 | Rolling update drops requests | **real bug found** | a few 502s/timeouts during every deploy | no preStop delay |
| 7 | Ingress hangs on 1 in 4 requests | real | requests hang forever, ~29% | dead nginx workers holding sockets |
| 8 | ArgoCD never in sync | real | StatefulSet always OutOfSync | defaulted fields missing from template |
| 9 | CI deploy fails at helm install | real | `failed calling webhook` | race with the ingress controller restart |
| 10 | Pipeline red on a green test suite | real | coverage 89.45% < 90% | new code with no tests |
| 11 | 500s while the HPA scales out | **real bug found** | 312 of 21,474 requests fail under load | liveness probe restarted Postgres |
| L1 | [`broken-image.yaml`](./broken-image.yaml) | manifest lab | `ImagePullBackOff` | tag never pushed |
| L2 | [`broken-service.yaml`](./broken-service.yaml) | manifest lab | connection refused, pods all Ready | selector matches no pods |

---

## 1. A typo in the database host

**Inject:** a hand edit of the ConfigMap, then an ordinary restart.

```bash
kubectl patch configmap kharcha-config -n kharcha-lab --type merge -p '{"data":{"DB_HOST":"kharcha-postgress"}}'
kubectl rollout restart deploy/kharcha-backend -n kharcha-lab
```

**Identify.** The new pod never gets past its init container and the rollout does not finish. Users see nothing yet, because `maxUnavailable: 0` keeps the old pods serving until a new one is Ready:

```text
kharcha-backend-6b6d677dfc-cm76v   true    Running   Completed   <none>
kharcha-backend-6b6d677dfc-gfv42   true    Running   Completed   <none>
kharcha-backend-75d85d65d8-866z2   false   Pending   <none>      PodInitializing

$ kubectl rollout status deploy/kharcha-backend -n kharcha-lab --timeout=5s
error: timed out waiting for the condition
frontend /api/expenses -> HTTP 200
```

**Investigate.** The init container is the one running `migrate`, so ask it, then check the name it is using against the Services that exist:

```text
$ kubectl logs -n kharcha-lab <new pod> -c migrate --tail=3
[db] not ready yet (OperationalError), retrying
$ kubectl get configmap kharcha-config -n kharcha-lab -o jsonpath='DB_HOST={.data.DB_HOST}'
DB_HOST=kharcha-postgress
$ kubectl get svc -n kharcha-lab | grep postgres
kharcha-postgres
kharcha-postgres-headless
$ kubectl exec -n kharcha-lab probe -- getent hosts kharcha-postgress
kharcha-postgress: no such host
```

**Root cause.** `kharcha-postgress` (two s) does not exist, so DNS fails and `wait_for_database()` retries until its 120 s budget runs out, after which the pod would crash-loop.

**Fix.** Re-apply the release. Helm 3 does a three-way merge against the *live* object, so it puts the hand-edited value back. Then restart so pods pick up the corrected env:

```bash
helm upgrade --install kharcha helm/kharcha -n kharcha-lab -f gitops/values-minikube.yaml ...
kubectl rollout restart deploy/kharcha-backend -n kharcha-lab
```

**Verify.** `DB_HOST=kharcha-postgres`, rollout finished, `frontend /api/expenses -> HTTP 200`.

**Prevention.** In the real namespace ArgoCD reverts a ConfigMap edit within seconds. The init container plus `maxUnavailable: 0` meant a bad config never took the app down, it only stalled the rollout.

## 1b. The same typo, first attempt: a bug in my own chart

My first way of injecting scenario 1 was through Helm values, `--set database.host=kharcha-postgress`. I expected stuck pods. Instead **everything went green**:

```text
kharcha-backend-5fdff8695f-hb2hq    true    Running   Completed   <none>
kharcha-postgress-0                 true    Running   <none>      <none>     <-- ?!
kharcha-backend-5fdff8695f-9pvh9    true    Running   Completed   <none>

$ kubectl logs <new pod> -c migrate --tail=4
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
[entrypoint] migrations done
```

A pod called `kharcha-postgress-0` existed. My chart named the bundled Postgres StatefulSet and Services with the same helper that resolves `database.host`. So the typo renamed the database itself: Helm created a **second, empty Postgres** under the wrong name, the init container happily migrated it, and the backend switched over with every probe passing. For a user, every expense they ever entered would have vanished, and no alert would have fired. The orphaned volume was still there afterwards:

```text
data-kharcha-postgres-0    Bound   1Gi
data-kharcha-postgress-0   Bound   1Gi
```

**Fix (commit f230138).** The bundled database now has a fixed name (`kharcha.postgresName`), and the chart refuses the combination at render time:

```text
$ helm template x helm/kharcha --set database.host=kharcha-postgress
Error: ... database.host is set while postgres.enabled=true. Use one or the other:
set postgres.enabled=false to use an external database.
```

The intended use (an external database such as RDS) still works: `--set database.host=<endpoint> --set postgres.enabled=false` renders `DB_HOST` as the endpoint and no StatefulSet at all.

**Lesson.** "The probes are green" and "the app is correct" are different claims. Readiness checks that *a* database answers, not that it is *the* database. If I had only tested the happy path, this would have shipped.

## 2. A release with an image tag that was never pushed

**Inject:** `helm upgrade ... --set images.tag=0000000`

**Identify.** New pods in `ImagePullBackOff`, old pods still serving:

```text
kharcha-backend-795c7f55ff-z86h7    false   Pending   ImagePullBackOff   PodInitializing
kharcha-frontend-554798ffc4-9tvw6   false   Pending   <none>             ImagePullBackOff
frontend /api/expenses -> HTTP 200
```

**Investigate.**

```text
$ kubectl describe pod <new frontend pod> | grep -E 'Image:|Failed'
    Image:  ghcr.io/lavya255/kharcha-frontend:0000000
  Warning  Failed  ... failed to resolve reference "ghcr.io/lavya255/kharcha-frontend:0000000": not found
```

**Root cause.** The tag does not exist. CI only pushes tags that passed the security gate; this one was typed by hand.

**Fix.** `helm rollback kharcha 0 -n kharcha-lab` (revision 0 means "the previous one").

**Verify.** Both Deployments back on `a5e2e0d`, 2/2 ready, API 200.

**Prevention.** Tags are always commit SHAs written by CI, never typed, and the chart refuses `latest`. With GitOps the only way to change the tag is a commit, which shows up in review and in `git log`.

## 3. Someone "rotates" the database password by re-creating the Secret

**Inject:**

```bash
kubectl delete secret kharcha-db -n kharcha-lab && bash kubernetes/create-db-secret.sh kharcha-lab
kubectl rollout restart deploy/kharcha-backend -n kharcha-lab
```

**Identify.** Running pods are fine (they read the env when they started). The next restart gets stuck in `Init`, retrying with `OperationalError`.

**Investigate.** `OperationalError` is vague. The database's own log is not:

```text
$ kubectl logs -n kharcha-lab kharcha-postgres-0 | grep FATAL
FATAL:  password authentication failed for user "kharcha"
```

**Root cause.** Postgres stores the password when its data directory is first initialised. `POSTGRES_PASSWORD` is ignored after that. The Secret now holds a new random password; the database still has the old one.

**Fix.** Make the database match the Secret. [`sync-db-password.sh`](./sync-db-password.sh) passes the password Secret, stdin, psql variable, so it is never printed and never visible in `ps`:

```text
$ bash troubleshooting/sync-db-password.sh kharcha-lab
postgres password for user kharcha now matches secret/kharcha-db in kharcha-lab
```

**Verify.** The stuck pods get in on their next retry, rollout completes.

**Prevention.** `create-db-secret.sh` only creates the Secret if it is missing, exactly so a re-run cannot do this. A real rotation is two steps in the other order: `ALTER USER` first, then update the Secret, then restart.

**Something else this scenario showed.** The final check after the fix timed out once (`HTTP 000`), even though the rollout said it was complete. That led to scenario 6.

## 4. A hand edit points the Service at the wrong port

**Inject:** `kubectl patch svc kharcha-backend ... targetPort 9000`

**Identify.** Every pod is Ready, yet every API call fails:

```text
frontend /api/expenses -> HTTP 502
```

**Investigate.** Walk the chain one hop at a time, frontend, Service, endpoints, pod:

```text
$ kubectl get endpointslices -l kubernetes.io/service-name=kharcha-backend
NAME                    PORT   ADDRESSES
kharcha-backend-4txm6   9000   10.244.0.51,10.244.0.52

$ curl http://<pod IP>:8000/health          # the pod itself
{"status":"UP","version":"a5e2e0d"}

$ curl http://kharcha-backend:8000/health   # through the Service
via the Service: curl exit 7, connection refused
```

The pod answers on 8000; the Service sends traffic to 9000.

**Fix.** Re-apply the chart; Helm's three-way merge restores `targetPort: http`.

**Verify.** `targetPort=http`, API 200.

**Prevention.** The chart uses a **named** port (`targetPort: http`), so changing the container port can never desync the two. And in the ArgoCD-managed namespace this exact edit was reverted in 2 seconds.

## 5. The scrape annotation is wrong: the app works, monitoring is blind

**Inject:** patch the pod template annotation `prometheus.io/port` to `9000`.

**Identify.** The app answers 200, but Prometheus shows the targets DOWN:

```text
kharcha-backend-dcb95df5f-9gr6m    down  Get "http://10.244.0.53:9000/metrics": dial tcp ...: connect: connection refused
frontend /api/expenses -> HTTP 200
```

**Investigate.** Prometheus builds the scrape URL from the pod's annotations, so compare them:

```text
$ kubectl get pod <backend> -o jsonpath='{.metadata.annotations}'
    "prometheus.io/port": "9000",
```

**Root cause.** Metrics are served on 8000, the annotation says 9000.

**Fix and verify.** Re-apply the chart; 45 s later both targets are `up`.

**Prevention.** The annotation is rendered from the same `backend.port` value as the container port, so the chart cannot produce this; only a hand edit can. In the real `kharcha` namespace the `KharchaBackendDown` alert (`sum(up{...backend}) < 1` for 1 minute) fires on exactly this. The lab namespace is deliberately outside that alert's scope.

## 6. Every rolling update dropped a few requests

Found because of the timeout at the end of scenario 3. The frontend's nginx log at that second:

```text
connect() failed (111: Connection refused) while connecting to upstream ... upstream: "http://10.102.253.195:8000/api/expenses"
upstream timed out (110: Operation timed out) while connecting to upstream ...
```

`10.102.253.195` is the backend **Service**, and it was routing to a pod that had already stopped listening.

**Measure it.** One request every 100 ms through the frontend for 45 s, while the backend does a plain `rollout restart`:

```text
BEFORE (no preStop)                 AFTER (preStop sleep 5)
requests during the rollout: 450    requests during the rollout: 450     (run 1)
  HTTP 000 (timeout) x 2              HTTP 200 x 450
  HTTP 200 x 445                    requests during the rollout: 450     (run 2)
  HTTP 502 x 3                        HTTP 200 x 450
```

**Root cause.** When Kubernetes terminates a pod, removing it from the Service endpoints and sending SIGTERM happen **at the same time**, not one after the other. uvicorn closes its socket immediately, but kube-proxy on the node is still routing new connections to that pod for a moment. Those get refused, and nginx turns that into a 502. `maxUnavailable: 0` does not help: it controls how many pods are missing, not this race.

**Fix (commit 13d2ad0).** A `preStop` hook that sleeps 5 seconds on both Deployments. Termination waits for the hook, so the pod keeps serving until it has left the endpoints, then shuts down. 5 failures in 450 became 0 in 900.

**Lesson.** About 1% of requests failing during deploys is easy to never notice in a dashboard. I only found it because one check happened to land in the window.

## 7. The Ingress hung on about 1 request in 4

**Identify.** Through the Ingress, roughly a quarter of requests hung until the client gave up. Straight to the pod IPs: 100% fine. So the problem was between the client and the backends.

```text
100 requests, 4s timeout each: ok=71 timed_out=29
```

**Investigate.** Rule out pieces one at a time:

- From **inside** the ingress controller pod to its own `127.0.0.1:80`: still hangs, so it is not hostPort/iptables.
- A request to a host with **no** Ingress rule (nginx answers 404 itself, no upstream at all): `ok=18 hung=22`. So it is nginx's own listener, not my app.
- nginx starts one worker per CPU the node shows: `worker_processes 24;` and 24 `reuseport` sockets on port 80. But only **17** workers were alive, and 7 of the listening sockets had connections queued that nobody would ever accept:

```text
00000000:0000000C 38642     <- 12 connections waiting, no worker
00000000:00000009 38641
00000000:00000008 38640
...
```

- Why: they died during the reload my `helm install` triggered:

```text
[alert] 851#851: pthread_create() failed (11: Resource temporarily unavailable)
[alert] 25#25: worker process 851 exited with fatal code 2 and cannot be respawned
pids.max=1400
```

**Root cause.** 24 workers, each with its own threads, ran into the container's pids limit (1400) during a reload. 7 of 24 workers could not start, their sockets stayed open, and the kernel kept handing them about 7/24 = 29% of new connections. That is exactly the hang rate.

**Fix.** [`kubernetes/tune-ingress-nginx.sh`](../kubernetes/tune-ingress-nginx.sh) sets `worker-processes: "4"` in the controller's ConfigMap and **restarts** it (a reload is not enough, the orphaned sockets belong to the master). After: 4 listeners, 4 workers, all queues empty, `ok=100 timed_out=0`. The CI kind cluster runs the same script.

**Same bug, my own app.** That made me check my frontend nginx: each pod, limited to 0.2 CPU, was also running **24 workers**. The image now pins `worker_processes 2`.

## 8. ArgoCD showed the Postgres StatefulSet OutOfSync forever

**Identify.** After handing the app to ArgoCD everything synced except the StatefulSet, which stayed `OutOfSync` no matter how often it synced.

**Investigate.** Compare the template with the live object:

```text
$ kubectl get sts kharcha-postgres -o jsonpath='{.spec.volumeClaimTemplates}'
"apiVersion": "v1", "kind": "PersistentVolumeClaim", ... "volumeMode": "Filesystem"
```

**Root cause.** The API server fills in `apiVersion`, `kind` and `volumeMode` on each volumeClaimTemplate. My template did not have them, so the rendered and live objects never matched. VolumeClaimTemplates are immutable, so ArgoCD could not "fix" it either.

**Fix.** Write those three defaults in the chart. Since they already equal the live values, applying them is a no-op on the immutable field. Result: `Synced / Healthy`.

## 9. CI failed at `helm install` with a webhook error

```text
Error: Internal error occurred: failed calling webhook "validate.nginx.ingress.kubernetes.io":
failed to call webhook: Post "https://ingress-nginx-controller-admission.ingress-nginx.svc..."
```

Every test and scan in that run had passed. The deploy job restarts the ingress controller (scenario 7's fix), and `deployment Available` came back before the new pod was serving the admission webhook. Two earlier runs had won that race. **Fix:** the job now retries a server-side dry run of an Ingress until the webhook answers, then installs.

## 10. The pipeline went red with every test passing

```text
FAIL Required test coverage of 90% not reached. Total coverage: 89.45%
============================== 28 passed ==============================
```

My local number said 96%, but it was from before I wrote `wait_for_database()`, so the retry loop that keeps pods out of a crash loop had **no tests**, and neither did the 503 branch of `/ready`, the whole point of a readiness probe. I added 5 tests (first-try success, retry until Postgres is up, give up after the timeout, session always closed, `/ready` 503 while `/health` stays 200). Now 33 tests, 100%. The coverage gate did its job.

## 11. Under load, a liveness probe restarted the database

Found while demonstrating the HPA with [`scripts/load-test.sh`](../scripts/load-test.sh) (40 workers through the Ingress for 4 minutes). The backend scaled 2 → 4 → 6 as designed, but:

```text
done: 21474 requests in 242s (~88 req/s), ok=21065 failed=409
```

**Investigate.** Split the failures by status in the ingress log, then read the backend's exceptions:

```text
  21065 200
    262 201
    103 499     <- client gave up after 5s, all at 19:23, before the HPA reacted
    312 500     <- the application failing

    132 psycopg.OperationalError: ... FATAL:  the database system is shutting down
    104 psycopg.OperationalError: ... port 5432 failed: Connection refused
     27 sqlalchemy.exc.OperationalError: (psycopg.errors.AdminShutdown) terminating connection due to administrator command
```

The database was going down in the middle of the test. Why:

```text
$ kubectl get pod kharcha-postgres-0
RESTARTS 1   LAST_REASON Completed   FINISHED 2026-10-16T19:25:11Z
Liveness probe failed: command timed out: "pg_isready ..." timed out after 1s
liveness={... "timeoutSeconds":1, "failureThreshold":3 ...}
19:26:30 postgres cpu cores: 0.5      <- exactly its 500m limit
```

**Root cause.** Six backend pods drove Postgres to its CPU limit, where it was throttled. `pg_isready` then took longer than its 1-second timeout, three times in a row, so the kubelet decided the database was dead and **restarted it in the middle of the load**. Every backend pod lost its connections at once. A liveness probe that cannot tell "busy" from "stuck" turns a slow database into a down one. It is the same lesson as the backend's `/health` not checking the database, one layer down.

**Fix (commit 790e12f).**

- Postgres liveness: 5 s timeout, 6 failures, so a full minute of no answer before a restart. Readiness timeout 3 s.
- Postgres CPU: request 250m, limit 1500m. One database serves every backend replica.
- Backend connection pool: 5 + 5 per pod with a 10 s timeout. At the HPA maximum of 6 pods that is at most 60 of Postgres's 100 connections (SQLAlchemy's default 5 + 10 would have been 90).

**Verify.** The identical test after the fix (`screenshots/terminal/38b-hpa-after-fix.png`):

```text
done: 33444 requests in 241s (~138 req/s), ok=33444 failed=0
19:40:57  cpu=951%  replicas current=6 desired=6  postgres restarts=0
kharcha-postgres-0   RESTARTS 0   READY true
```

More throughput (138 req/s instead of 88) and not one failed request, with the HPA going 2 → 4 → 6 exactly as before.

## Manifest labs (from the course guide)

Self-contained broken YAML, applied into the lab namespace. Each one passes the restricted Pod Security policy, so the only thing wrong is the bug. (The first version of `broken-image.yaml` did not: the pipeline's config scan failed it for a missing read-only root filesystem, which is now fixed.)

### L1. `broken-image.yaml`

```text
$ kubectl get pods -l app=broken-image
broken-image-...   0/1   ImagePullBackOff
$ kubectl describe pod -l app=broken-image
    Image:  ghcr.io/lavya255/kharcha-frontend:does-not-exist
  Warning  Failed  ... Error: ImagePullBackOff
$ kubectl set image deploy/broken-image web=ghcr.io/lavya255/kharcha-frontend:ac8a8d7
broken-image-...   true   Running   ghcr.io/lavya255/kharcha-frontend:ac8a8d7
```

### L2. `broken-service.yaml`

A Service whose selector says `component: api` next to pods labelled `component: backend`:

```text
$ curl http://backend-broken:8000/health
curl exit 7: nothing behind the Service
$ kubectl get endpointslices -l kubernetes.io/service-name=backend-broken
backend-broken-t5x68   <none>
$ kubectl get svc backend-broken -o jsonpath='{.spec.selector}'
{"app.kubernetes.io/component":"api", ...}
$ kubectl get pods --show-labels   ->   app.kubernetes.io/component=backend, ...
$ kubectl patch svc backend-broken ... '{"spec":{"selector":{"app.kubernetes.io/component":"backend"}}}'
backend-broken-t5x68   10.244.0.77,10.244.0.76
{"status":"UP","version":"a5e2e0d"}
```

A Service finds its pods only by labels. One wrong value means no endpoints, while every pod looks healthy.

Captures: `screenshots/terminal/39-lab-broken-image.png`, `40-lab-broken-service.png`.

---

## ArgoCD self-heal: the same mistakes in the real namespace

The lab needed a human for scenarios 1 and 4. In the namespace ArgoCD manages, they fix themselves:

```text
$ kubectl patch svc kharcha-backend -n kharcha ... targetPort 9000      17:03:39
  17:03:41  targetPort back to 'http' after 2s
$ kubectl scale deploy/kharcha-frontend -n kharcha --replicas=5         17:03:41
  17:03:43  frontend replicas back to '2' after 2s
$ kubectl delete configmap kharcha-config -n kharcha                     17:03:43
  17:03:49  kharcha-config back to 'configmap/kharcha-config' after 6s
```

## A debugging checklist I now actually use

1. **Where does it break?** Test each hop separately: Ingress, frontend Service, frontend pod, backend Service, backend pod IP, database. The first hop that fails is the one to look at.
2. **Pods:** `kubectl get pods` (look at READY and the INIT column, not just STATUS), `kubectl describe pod` (Events at the bottom), `kubectl logs <pod> -c <init container>`.
3. **The other side's log.** The client said `OperationalError`; Postgres said exactly which user failed and why.
4. **Services:** `kubectl get endpointslices` shows which pods and which port a Service really sends to.
5. **Rollouts:** `helm history` and `helm rollback`, or under GitOps, `git revert`.
6. **Numbers, not impressions.** "Sometimes slow" became "29 of 100" and "5 of 450", which is what made both root causes findable.
