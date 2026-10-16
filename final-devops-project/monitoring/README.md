# Monitoring

Prometheus scrapes the backend, kube-state-metrics and the node; Grafana shows one dashboard built for this app. Everything is code: chart versions pinned, values in git, the data source and the dashboard provisioned, nothing clicked together in a UI.

```bash
./monitoring/install.sh          # Prometheus + Grafana into namespace "monitoring"
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
kubectl port-forward -n monitoring svc/grafana 3001:80
```

| File | What |
| --- | --- |
| [`install.sh`](./install.sh) | Idempotent install: namespace, both charts, the dashboard ConfigMap |
| [`prometheus-values.yaml`](./prometheus-values.yaml) | prometheus-community/prometheus 29.37.0 (Prometheus v3.15.0), alert rules |
| [`grafana-values.yaml`](./grafana-values.yaml) | grafana/grafana 10.5.15 (Grafana 12.3.1), provisioned data source, dashboard sidecar |
| [`dashboards/kharcha.json`](./dashboards/kharcha.json) | The dashboard, 16 panels |

## How the app gets scraped

The backend exposes `/metrics` (prometheus_client). The chart puts three annotations on the backend pods:

```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8000"
prometheus.io/path: /metrics
```

The chart's built-in `kubernetes-pods` job discovers any annotated pod. A new pod (a rollout, an HPA scale-up) is scraped as soon as it exists, with no scrape config to keep in sync with the deployment. Pod labels come along as metric labels, which is why queries can filter on `app_kubernetes_io_component="backend"`.

```text
kubernetes-nodes               https://192.168.49.2:10250/metrics           up
kubernetes-nodes-cadvisor      https://192.168.49.2:10250/metrics/cadvisor  up
kubernetes-pods                kharcha-backend-5dc98f56b8-ctbxc             up
kubernetes-pods                kharcha-backend-5dc98f56b8-sct8l             up
```

## What the app exports

| Metric | Type | Labels | Why |
| --- | --- | --- | --- |
| `kharcha_http_requests_total` | counter | method, route, status | traffic and errors |
| `kharcha_http_request_duration_seconds` | histogram | method, route | latency percentiles |
| `kharcha_expenses_created_total` | counter | category | business: are people using it |
| `kharcha_amount_spent_total` | counter | category | business: money recorded |
| `kharcha_app_info` | gauge (=1) | version | which commit is running, rollouts visible on a graph |

`route` is the route **template** (`/api/expenses/{expense_id}`), never the raw path. Raw paths would create one time series per expense ID, unbounded cardinality, which is the classic way to take down a Prometheus server. A test checks this.

## The dashboard

![Grafana dashboard](../screenshots/09-grafana-dashboard.jpg)

- **Golden signals:** running version(s), backend pods up, requests/s, 5xx rate, p95 latency, expenses added.
- **Request rate by route**, **latency p50/p95/p99**, **responses by status code** (stacked), **money by category**.
- **Kubernetes:** CPU and memory per pod (cAdvisor), HPA current/desired/max replicas, container restarts (kube-state-metrics).

With the load generator running: about 10.9 req/s, p95 4.88 ms, 0% 5xx, and a mix of 200/201/404/422 on the status graph (the 404s and 422s are deliberate bad requests).

Three panels were wrong the first time I saw them with real data, all for PromQL reasons worth knowing:

| Panel | What it showed | Why | Fix |
| --- | --- | --- | --- |
| 5xx error rate | **No data** | With zero 5xx responses the series does not exist, and `sum()` of nothing is nothing, not 0 | `(sum(...) or vector(0))` |
| Expenses added (1h) | **0** after a rollout, with expenses being added | `increase()` cannot see a counter's first increment on a brand-new pod | Show the total since the pods started, and say so |
| Running version | the same tag once per pod | `kharcha_app_info` has one series per pod | `count by (version) (kharcha_app_info)`: one entry per version, two during a rollout |

## Alerts

Evaluated by Prometheus even without Alertmanager (visible at `/alerts`, all five loaded and inactive). Wiring them to Slack or email is one Alertmanager away.

| Alert | Expression (short) | For |
| --- | --- | --- |
| KharchaBackendDown | `sum(up{namespace="kharcha", component="backend"}) < 1` | 1m |
| KharchaHighErrorRate | 5xx share of requests > 5% | 2m |
| KharchaSlowRequests | p95 > 500 ms (excluding `/health`) | 5m |
| KharchaPodRestarting | > 2 restarts in 15m | |
| KharchaHPAAtMax | current replicas >= max replicas | 10m |

## Choices

- **No persistent storage for Grafana.** Everything in it comes from git, so losing the pod loses nothing.
- **Prometheus keeps 3 days on a 2 GiB volume.** Enough to compare before and after a deploy on a laptop.
- **Anonymous read-only Grafana, local cluster only.** Viewers can look but not edit, so screenshots and port-forwards do not need the admin password (which the chart generates into a Secret). Not something to copy to an internet-facing Grafana; the values file says so.
- **The `monitoring` namespace is not "restricted"** like the app's: node-exporter needs the host's network and `/proc`, which that profile forbids.
- **Monitoring the monitoring found a real bug:** a wrong scrape annotation leaves the app fine and the dashboard blind ([troubleshooting scenario 5](../troubleshooting/README.md#5-the-scrape-annotation-is-wrong-the-app-works-monitoring-is-blind)).

Captures: `screenshots/07-prometheus-targets.jpg`, `08-prometheus-alert-rules.jpg`, `09-grafana-dashboard.jpg`, `terminal/22-monitoring-install.png`, `terminal/23-prometheus.png`.
