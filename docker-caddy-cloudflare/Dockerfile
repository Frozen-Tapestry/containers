# syntax=docker/dockerfile:1

ARG CADDY_VERSION=2.10.2

FROM docker.io/library/caddy:${CADDY_VERSION}-builder AS builder
RUN xcaddy build \
  --with github.com/caddy-dns/cloudflare

FROM docker.io/library/caddy:${CADDY_VERSION} AS caddy
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
