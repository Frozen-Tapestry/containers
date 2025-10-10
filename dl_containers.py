#!/usr/bin/env python3
from download_github_tree import download_github_tree

download_github_tree("https://github.com/linuxserver/docker-baseimage-alpine/tree/3.22")
download_github_tree("https://github.com/bitnami/containers/tree/main/bitnami/openldap")
# original: "https://github.com/MatthewVance/unbound-docker/tree/master/1.22.0"
download_github_tree("https://github.com/mastermc0/unbound-docker/tree/master/1.23.0", "unbound")
download_github_tree("https://github.com/IAreKyleW00t/docker-caddy-cloudflare/tree/main")
download_github_tree("https://github.com/linuxserver/docker-healthchecks/tree/master")
download_github_tree("https://github.com/Monogramm/autodiscover-email-settings/tree/master")
