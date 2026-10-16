# GitOps

Git is the only way anything changes in the `kharcha` namespace. CI never runs `kubectl` or `helm` against my cluster. Its last job is a **commit**, and ArgoCD, running inside the cluster, pulls that commit and makes the cluster match.

```text
 push to main
     │
     ▼
 GitHub Actions: test, scan, build, gate, push image ghcr.io/lavya255/kharcha-*:<sha>,
                 deploy to a throwaway kind cluster and smoke test it
     │
     ▼  last job: commit "GitOps: deploy kharcha <sha>"  (values-minikube.yaml, tag: "<sha>")
 git (main)
     │
     ▼  ArgoCD polls every 3 minutes
 ArgoCD in Minikube ── renders helm/kharcha + values-minikube.yaml ──► kharcha namespace
```

Two files:

- [`argocd-application.yaml`](./argocd-application.yaml): the Application. Applied once by hand; it lives outside the chart so ArgoCD is not managing its own definition.
- [`values-minikube.yaml`](./values-minikube.yaml): this environment's values on top of the chart defaults. The image tag in it is the only line CI ever changes.

## Why pull and not push

- **No cluster credentials in CI.** A push-based deploy would need a kubeconfig stored as a GitHub secret. Here the cluster reaches out to GitHub; nothing reaches in. My Minikube is not even reachable from the internet, and it does not need to be.
- **The repo is the audit log.** "What is running and who changed it" is `git log gitops/values-minikube.yaml`. Rolling back is `git revert`.
- **Drift gets fixed, not just reported.** With `selfHeal: true` a hand edit is reverted in seconds (below).

## Decisions in the Application

| Setting | Why |
| --- | --- |
| `automated: {prune, selfHeal}` | Git is the source of truth in both directions: removed from git means removed from the cluster, changed in the cluster means changed back. |
| `CreateNamespace=false` | The namespace carries Pod Security labels, a quota and the generated DB Secret from the bootstrap step. A bare namespace created by ArgoCD would have none of that. |
| `ServerSideApply=true` | Fields owned by other controllers (the HPA's replica count) are never fought over. |
| `ignoreDifferences` on backend `/spec/replicas` + `RespectIgnoreDifferences` | The HPA owns the backend's replica count. The chart already leaves `replicas` out when autoscaling is on; this is the second safety. |
| `retry` with backoff | A sync that races a webhook or a slow pod tries again instead of sitting in Failed. |
| Migrations in an **init container**, not a Helm hook | ArgoCD maps Helm `pre-upgrade` hooks to `PreSync`, which would run the migration before Postgres exists on the very first sync and deadlock. The init container waits for the database and a Postgres advisory lock stops two pods migrating at once. |

## Handing an existing helm release over to ArgoCD

The app was first installed with the helm CLI. I uninstalled the release and applied the Application. The Postgres volume and the generated Secret are not part of the release, so they survived, and so did the data:

```text
$ helm uninstall kharcha -n kharcha --wait
$ kubectl get pvc,secret -n kharcha
persistentvolumeclaim/data-kharcha-postgres-0   Bound   1Gi
secret/kharcha-db                               Opaque  1
$ kubectl apply -f gitops/argocd-application.yaml
...
expenses: 8  total: 17868.50  used: 89.3 %
```

From that point the images came straight from GHCR (CI's packages inherit the public repo's visibility), pulled by digest:

```text
ghcr.io/lavya255/kharcha-backend@sha256:8bcb3fedff59780b2f412c6fd1e30dd6b571a5a6abdbc3e0c1c71bde78026f70
```

Full capture: `screenshots/terminal/21-gitops-handover.png`.

## The live demo: one commit to running pods

Commit `58af10d` carried a visible change (a "per day so far" pace on the Spent card). Times are UTC:

| Time | What happened | Who |
| --- | --- | --- |
| 16:53:18 | push to main, pipeline starts | me |
| 16:55:07 | all tests and scans green, security gate passes | GitHub Actions |
| 16:55:32 | both images pushed to GHCR as `:58af10d` | GitHub Actions |
| 16:57:19 | deployed to a kind cluster, smoke test and `helm test` pass | GitHub Actions |
| 16:57:24 | `GitOps: deploy kharcha 58af10d [skip ci]` committed | github-actions[bot] |
| 16:59:50 | ArgoCD sees the new commit and starts the rollout | ArgoCD |
| 17:00:10 | all four app pods on `58af10d`, `/health` says `{"version":"58af10d"}` | Kubernetes |

About 7 minutes from `git push` to new pods serving, with no `kubectl` typed by anyone. The watch, collapsed:

```text
16:58:23  argocd=Synced/Healthy      running images: 4 a5e2e0d
   ... same state, polled every ~5s until 16:59:47 (ArgoCD polls git every 3 minutes)
16:59:52  argocd=Synced/Progressing  running images: 4 a5e2e0d
16:59:58  argocd=Synced/Progressing  running images: 2 58af10d   4 a5e2e0d
17:00:04  argocd=Synced/Progressing  running images: 3 58af10d   2 a5e2e0d
17:00:10  argocd=Synced/Healthy      running images: 4 58af10d
```

New pods come up before old ones go (`maxUnavailable: 0`), which is why the count briefly goes above four. Before and after in the browser: `screenshots/04-demo-before-top.jpg`, `05-demo-before-footer.jpg` (API `619d00a`), `06-demo-after-top.jpg`, `06-demo-after-footer.jpg` (API `58af10d`). The Grafana "Running version" panel showed both versions during the switch (`09-grafana-dashboard.jpg`).

The extra 172 "Traffic test" expenses in the after screenshot come from the load generator I ran so the monitoring graphs had real traffic. They are marked "load generator" in the note field.

## Self-heal

```text
$ kubectl patch svc kharcha-backend -n kharcha ... targetPort 9000      17:03:39
  17:03:41  targetPort back to 'http' after 2s
$ kubectl scale deploy/kharcha-frontend -n kharcha --replicas=5         17:03:41
  17:03:43  frontend replicas back to '2' after 2s
$ kubectl delete configmap kharcha-config -n kharcha                     17:03:43
  17:03:49  kharcha-config back to 'configmap/kharcha-config' after 6s
```

## Things that bit me

- **Ever-OutOfSync StatefulSet.** The API server adds `apiVersion`, `kind` and `volumeMode` to volumeClaimTemplates. Until the chart wrote them out, ArgoCD saw a permanent diff. Details in [troubleshooting](../troubleshooting/README.md#8-argocd-showed-the-postgres-statefulset-outofsync-forever).
- **A bot commit must not start another pipeline.** Pushes made with `GITHUB_TOKEN` do not trigger workflows, and the message also carries `[skip ci]`, so the bump cannot loop.
- **An older, slower run must not roll the environment back.** The bump job checks that the tag already in git is an ancestor of its own commit before replacing it.
- **Two jobs pushing to main at once.** The bump does `git pull --rebase` and retries the push up to three times.

## Rolling back

```bash
git revert <the GitOps bump commit>     # ArgoCD rolls back to the previous tag
git push
```

Or, in an emergency, disable auto-sync in ArgoCD first and `helm rollback`, then fix git. Otherwise self-heal will undo the rollback, which is the point.
