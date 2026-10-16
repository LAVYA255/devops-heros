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
RUN rm -f /etc/nginx/conf.d/default.conf \
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
