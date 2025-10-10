# syntax=docker/dockerfile:1
FROM docker.io/library/caddy:2.10.2-builder AS builder
RUN xcaddy build \
  --with github.com/caddy-dns/cloudflare

FROM docker.io/library/caddy:2.10.2 AS caddy
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
