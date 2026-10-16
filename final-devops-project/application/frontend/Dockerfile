# ---------------------------------------------------------------------------
# Stage 1: build the React app with Node. None of this ends up in the final
# image: no node_modules, no Node runtime, no build tooling.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app
# Copy only the manifests first so the `npm ci` layer is cached until the
# dependencies actually change, not on every source edit.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2: serve the static files with nginx, as a non-root user.
# nginx-unprivileged runs as uid 101 and listens on 8080, so it never needs
# root to bind a low port.
# ---------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.29-alpine

# Same-origin by default: /api is proxied to the backend service.
ENV BACKEND_UPSTREAM=http://backend:8000 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

USER root
# Trivy found 43 fixable HIGH CVEs in the base image's Alpine packages (curl,
# openssl, expat, pcre2, ...). Upgrade what has a fix, and drop curl entirely:
# nothing here uses it (the healthcheck is busybox wget), so it is pure
# attack surface.
#
# worker_processes: the stock config says "auto", which means one worker per
# CPU on the NODE, not per CPU the container is allowed. A pod limited to 0.2
# CPU on my 24-core laptop was running 24 workers (the same sizing that broke
# the ingress controller). It is fixed at build time because the pod's root
# filesystem is read-only, so nothing can rewrite nginx.conf at startup. More
# traffic means more replicas, not more workers per pod.
RUN apk upgrade --no-cache \
    && apk del --no-cache curl \
    && sed -i 's/^worker_processes.*/worker_processes  2;/' /etc/nginx/nginx.conf \
    && rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /etc/nginx/snippets
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
# The envsubst step writes the rendered config into conf.d at startup, so the
# non-root user must own that directory.
RUN chown -R 101:101 /etc/nginx/conf.d /usr/share/nginx/html
USER 101

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
