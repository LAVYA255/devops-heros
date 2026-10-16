{{/* Base name: release-chart, trimmed to the 63 char DNS label limit. */}}
{{- define "kharcha.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "kharcha.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ include "kharcha.tag" . | quote }}
app.kubernetes.io/part-of: kharcha
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* Selector labels must never change after install: Deployment selectors are immutable. */}}
{{- define "kharcha.selector" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* The image tag: images.tag if set, else the chart appVersion. Fails loudly on "latest". */}}
{{- define "kharcha.tag" -}}
{{- $tag := default .Chart.AppVersion .Values.images.tag -}}
{{- if eq (toString $tag) "latest" -}}
{{- fail "images.tag must be a commit SHA, not 'latest'" -}}
{{- end -}}
{{- $tag -}}
{{- end -}}

{{- define "kharcha.backendImage" -}}
{{- printf "%s/%s:%s" .Values.images.registry .Values.backend.image (include "kharcha.tag" .) -}}
{{- end -}}

{{- define "kharcha.frontendImage" -}}
{{- printf "%s/%s:%s" .Values.images.registry .Values.frontend.image (include "kharcha.tag" .) -}}
{{- end -}}

{{- define "kharcha.dbHost" -}}
{{- printf "%s-postgres" (include "kharcha.fullname" .) -}}
{{- end -}}

{{/* Pod-level hardening shared by every workload. Satisfies the "restricted" Pod Security Standard. */}}
{{- define "kharcha.podSecurity" -}}
runAsNonRoot: true
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "kharcha.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{/*
Database environment. The password comes from the Secret, then DATABASE_URL is
assembled with Kubernetes' $(VAR) expansion, which only substitutes variables
defined EARLIER in the same env list. So the order of these entries matters.
*/}}
{{- define "kharcha.dbEnv" -}}
- name: DB_HOST
  valueFrom:
    configMapKeyRef:
      name: {{ include "kharcha.fullname" . }}-config
      key: DB_HOST
- name: DB_NAME
  valueFrom:
    configMapKeyRef:
      name: {{ include "kharcha.fullname" . }}-config
      key: DB_NAME
- name: DB_USER
  valueFrom:
    configMapKeyRef:
      name: {{ include "kharcha.fullname" . }}-config
      key: DB_USER
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.database.existingSecret }}
      key: password
- name: DATABASE_URL
  value: "postgresql+psycopg://$(DB_USER):$(DB_PASSWORD)@$(DB_HOST):5432/$(DB_NAME)"
{{- end -}}
