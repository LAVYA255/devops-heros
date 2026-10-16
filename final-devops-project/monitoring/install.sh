#!/usr/bin/env bash
# Installs Prometheus + Grafana into the "monitoring" namespace and loads the
# Kharcha dashboard. Safe to run again: every step is an upgrade/apply.
#
#   ./monitoring/install.sh
#
# Then:
#   kubectl port-forward -n monitoring svc/prometheus-server 9090:80
#   kubectl port-forward -n monitoring svc/grafana 3001:80
set -euo pipefail
cd "$(dirname "$0")"

PROM_CHART_VERSION=29.37.0
GRAFANA_CHART_VERSION=10.5.15

# Not labelled "restricted" like the app namespace: node-exporter needs the
# host's network and /proc to report node metrics, which that profile forbids.
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update prometheus-community grafana >/dev/null

helm upgrade --install prometheus prometheus-community/prometheus \
  --version "$PROM_CHART_VERSION" -n monitoring -f prometheus-values.yaml \
  --wait --timeout 6m

# The dashboard JSON lives in git. The sidecar in the Grafana pod watches for
# ConfigMaps with this label and loads them as dashboards.
kubectl create configmap kharcha-dashboard -n monitoring \
  --from-file=kharcha.json=dashboards/kharcha.json \
  --dry-run=client -o yaml \
  | kubectl label --local -f - grafana_dashboard=1 -o yaml \
  | kubectl apply -f -

helm upgrade --install grafana grafana/grafana \
  --version "$GRAFANA_CHART_VERSION" -n monitoring -f grafana-values.yaml \
  --wait --timeout 6m

kubectl get pods -n monitoring
