# containers

This repo fetches, builds, and publishes container images used by Frozen Tapestry projects.

---

## Overview

* **`setup.py`** – main script to download source trees, fix Dockerfiles, and apply text replacements.
* **`download_github_tree.py`** – generic GitHub subtree downloader.
* **`hub_full_paths.py`** – normalizes `FROM` lines to full Docker Hub paths.
* **`replace_in_dir.py`** – utility for recursive multi-string replacements.

---

## Build & Publish

Images are built automatically via **GitHub Actions** (`.github/workflows/build-containers.yml`).

Published images:  
- `ghcr.io/frozen-tapestry/openldap`  
- `ghcr.io/frozen-tapestry/unbound`  
- `ghcr.io/frozen-tapestry/autodiscover`  
- `ghcr.io/frozen-tapestry/caddy-cloudflare`  
- `ghcr.io/frozen-tapestry/baseimage-alpine`  
- `ghcr.io/frozen-tapestry/healthchecks`

Each image builds from its subfolder (`mount_ws`) and is tagged with `latest` and a version (e.g. `:3.22`, `:1.23.0`).

---

## Manual Usage

```bash
# Full setup (download + fix + replace)
python3 setup.py
```

Or run individual steps:

```bash
python3 download_github_tree.py <github-tree-url>
python3 hub_full_paths.py
```

Optional:

```bash
export GITHUB_TOKEN=ghp_yourtoken  # for higher GitHub API limits
```

---