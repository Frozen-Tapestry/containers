#!/usr/bin/env python3
"""
Download a folder (or the whole repo) from a GitHub tree URL, preserving
the permissions Git actually stores:
- executable bit on regular files
- symlinks (where the OS/filesystem allows)
Submodules are skipped.

Defaults to using the tarball of the ref (1 request, preserves modes/symlinks).
Optionally use the Git Trees+Blobs API (per-file) with --mode=api to demonstrate
explicit mode handling.

Usage:
  python download_github_tree.py <github-tree-url> [target_dir] [--mode=tar|api]

Examples:
  python download_github_tree.py https://github.com/bitnami/containers/tree/main/bitnami/openldap
  python download_github_tree.py https://github.com/OWNER/REPO/tree/BRANCH/sub/dir outdir --mode=api

Notes:
- Provide a token via GITHUB_TOKEN env var for higher limits on api.github.com requests.
- Raw downloads do not use Authorization; tarball and API calls do.
"""

import base64
import io
import json
import os
import re
import stat
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "github-recursive-downloader/2.0 (+https://example.local)"
API_VERSION = "2022-11-28"

# ---------------------------
# URL parsing / target naming
# ---------------------------


def parse_github_tree_url(url: str) -> tuple[str, str, str, str]:
    """
    Parse a GitHub tree URL like:
      https://github.com/{owner}/{repo}/tree/{branch}/{path...}
    Returns (owner, repo, branch, path)
    Path may be "" for the repo root at that branch.
    """
    parsed = urllib.parse.urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 4 or parts[2] != "tree":
        raise ValueError(
            "URL must be a GitHub tree URL like https://github.com/<owner>/<repo>/tree/<branch>/<path>"
        )
    owner = parts[0]
    repo = parts[1]
    branch = parts[3]
    path = "/".join(parts[4:]) if len(parts) > 4 else ""
    return owner, repo, branch, path


def target_dir_from_url(url: str, path: str) -> str:
    """
    Use the last component of the tree path as target directory.
    If the path is empty, fall back to the repo name.
    """
    parsed = urllib.parse.urlparse(url)
    parts = parsed.path.strip("/").split("/")
    repo = parts[1] if len(parts) >= 2 else "repo_download"
    if path:
        last = path.rstrip("/").split("/")[-1]
        return last or repo
    return repo


# ---------------------------
# HTTP helpers
# ---------------------------


def build_api_headers(token: str | None = None) -> dict:
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def github_api_request(
    url: str, token: str | None = None, retries: int = 4, initial_backoff: float = 1.0
):
    """
    Request JSON from api.github.com with sane headers + backoff on 403
    (rate limit / abuse detection). Raises RuntimeError with helpful details.
    """
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=build_api_headers(token))
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")
            # Capture rate headers if present
            rate_remaining = e.headers.get("X-RateLimit-Remaining")
            rate_reset = e.headers.get("X-RateLimit-Reset")
            if e.code == 403 and ("rate" in body.lower() or "abuse" in body.lower()):
                # Exponential backoff
                sleep_s = initial_backoff * (2**attempt)
                print(
                    f"GitHub 403 (remaining={rate_remaining}, reset={rate_reset}); "
                    f"backing off {sleep_s:.1f}s..."
                )
                time.sleep(sleep_s)
                continue
            raise RuntimeError(
                f"GitHub API error {e.code} for {url} "
                f"(remaining={rate_remaining}, reset={rate_reset}): {body}"
            ) from e
        except urllib.error.URLError as e:
            # Transient network error; backoff
            sleep_s = initial_backoff * (2**attempt)
            print(f"Network error {e}; retrying in {sleep_s:.1f}s...")
            time.sleep(sleep_s)
            continue
    raise RuntimeError("Exceeded retries due to rate limiting or network issues.")


# ---------------------------
# Trees + Blobs (permissions-aware API mode)
# ---------------------------

GIT_API_BASE = "https://api.github.com/repos/{owner}/{repo}/git"


def get_tree(owner: str, repo: str, ref: str, token: str | None = None):
    url = f"{GIT_API_BASE.format(owner=owner, repo=repo)}/trees/{urllib.parse.quote(ref)}?recursive=1"
    data = github_api_request(url, token=token)
    if data.get("truncated"):
        print(
            "Warning: tree response was truncated; very large repos may need tarball mode."
        )
    return data["tree"]


def get_blob(owner: str, repo: str, sha: str, token: str | None = None) -> bytes:
    url = f"{GIT_API_BASE.format(owner=owner, repo=repo)}/blobs/{sha}"
    data = github_api_request(url, token=token)
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"])
    return data["content"].encode("utf-8")


def ensure_dir(path: str):
    if path:
        os.makedirs(path, exist_ok=True)


def apply_mode(dest_path: str, mode: str):
    # Git only stores exec bit on regular files.
    if mode == "100755":
        st = os.stat(dest_path)
        os.chmod(dest_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def path_is_under(prefix: str, p: str) -> bool:
    if not prefix:
        return True
    prefix = prefix.rstrip("/")
    return p == prefix or p.startswith(prefix + "/")


def sync_with_permissions_api(
    owner: str,
    repo: str,
    branch: str,
    path: str,
    out_dir: str,
    token: str | None = None,
):
    """
    Use the Git Trees/Blobs API so we can see modes (100644/100755/120000/160000).
    - Regular file: write and set exec bit if 100755
    - Symlink (120000): create a symlink; blob content is the link target (text)
    - Submodule (160000): skip
    """
    tree = get_tree(owner, repo, branch, token=token)
    wanted = [e for e in tree if path_is_under(path, e["path"])]
    strip_prefix = (path.rstrip("/") + "/") if path else ""

    for entry in wanted:
        mode = entry.get("mode")
        etype = entry.get("type")  # 'blob', 'tree', or 'commit' for submodule
        tpath = entry["path"]
        rel = (
            tpath[len(strip_prefix) :]
            if strip_prefix and tpath.startswith(strip_prefix)
            else (tpath if not path else "")
        )
        if not rel:
            # the directory node itself
            continue
        dest = os.path.join(out_dir, rel)

        if mode == "040000" or etype == "tree":
            ensure_dir(dest)
            continue

        if mode == "160000" or etype == "commit":
            print(f"Skipping submodule: {rel}")
            continue

        if mode == "120000":
            blob = get_blob(owner, repo, entry["sha"], token=token)
            target = blob.decode("utf-8").rstrip("\n")
            ensure_dir(os.path.dirname(dest))
            try:
                os.symlink(target, dest)
                print(f"Created symlink: {rel} -> {target}")
            except (NotImplementedError, OSError):
                # Fallback for platforms without symlink support
                print(
                    f"Could not create symlink for {rel}; writing a text file with the target instead."
                )
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(target + "\n")
            continue

        if etype == "blob" and mode in ("100644", "100755"):
            ensure_dir(os.path.dirname(dest))
            data = get_blob(owner, repo, entry["sha"], token=token)
            with open(dest, "wb") as f:
                f.write(data)
            apply_mode(dest, mode)
            print(f"Downloaded file: {rel} ({mode})")
            continue

        print(f"Skipping unsupported entry: {rel} (mode={mode}, type={etype})")


# ---------------------------
# Tarball mode (fast, preserves perms/symlinks)
# ---------------------------


def _safe_extract_filter(m: tarfile.TarInfo) -> tarfile.TarInfo | None:
    # Prevent path traversal; strip leading slashes.
    if m is None:
        return None
    if m.name.startswith("/") or ".." in m.name.replace("\\", "/").split("/"):
        return None
    return m


def _extract_selected_from_tar(
    tf: tarfile.TarFile,
    repo_root: str,
    wanted_subpath: str,
    out_dir: str,
):
    """
    Extract only members under repo_root/wanted_subpath into out_dir,
    preserving exec bits and symlinks where possible.
    """
    # Normalize
    repo_root = repo_root.rstrip("/")
    wanted_subpath = wanted_subpath.strip("/")
    prefix = repo_root if not wanted_subpath else f"{repo_root}/{wanted_subpath}"

    # Iterate members once; manually extract to handle symlinks robustly.
    for m in tf.getmembers():
        if _safe_extract_filter(m) is None:
            continue
        if not (m.name == prefix or m.name.startswith(prefix + "/")):
            continue

        rel = m.name[len(prefix) :].lstrip("/")
        if rel == "":
            # top dir of the selection; ensure out_dir exists
            os.makedirs(out_dir, exist_ok=True)
            continue

        dest = os.path.join(out_dir, rel)
        dest_parent = os.path.dirname(dest)
        os.makedirs(dest_parent, exist_ok=True)

        if m.islnk():
            # Hard links inside archives are rare in GitHub tarballs; treat as regular file copy
            try:
                src = os.path.join(out_dir, m.linkname)
                with open(src, "rb") as s, open(dest, "wb") as d:
                    d.write(s.read())
            except Exception:
                # Fallback: materialize from file content if possible
                f = tf.extractfile(m)
                if f:
                    with open(dest, "wb") as d:
                        d.write(f.read())
            continue

        if m.issym():
            target = m.linkname
            try:
                os.symlink(target, dest)
            except (NotImplementedError, OSError):
                # Fallback: write a text file indicating target
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(target + "\n")
            continue

        if m.isdir():
            os.makedirs(dest, exist_ok=True)
            continue

        # Regular file
        f = tf.extractfile(m)
        if f is None:
            # Unexpected; skip
            continue
        with open(dest, "wb") as d:
            d.write(f.read())

        # Apply exec bit if present in mode
        file_mode = m.mode
        if file_mode & stat.S_IXUSR:
            st = os.stat(dest)
            os.chmod(dest, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def download_tarball_and_extract(
    owner: str,
    repo: str,
    ref: str,
    path: str,
    out_dir: str,
    token: str | None = None,
):
    """
    Download the tarball of a ref and extract only the desired subpath to out_dir.
    This preserves exec bits and symlinks (subject to OS support).
    """
    tar_url = (
        f"https://api.github.com/repos/{owner}/{repo}/tarball/{urllib.parse.quote(ref)}"
    )
    req = urllib.request.Request(tar_url, headers=build_api_headers(token))
    print(f"Fetching tarball for {owner}/{repo}@{ref} ...")
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        raise RuntimeError(f"Tarball HTTP error {e.code}: {body}") from e

    # Open tar from memory (data is typically gzipped tar)
    fileobj = io.BytesIO(data)
    try:
        with tarfile.open(fileobj=fileobj, mode="r:*") as tf:
            # The tarball has a single top-level dir like owner-repo-<sha>/
            # Detect it from the first member
            names = tf.getnames()
            if not names:
                raise RuntimeError("Empty tarball.")
            toplevel = names[0].split("/")[0]
            _extract_selected_from_tar(tf, toplevel, path, out_dir)
    except tarfile.ReadError as e:
        raise RuntimeError(f"Failed to read tarball: {e}") from e


# ---------------------------
# Public entry point
# ---------------------------


def download_github_tree(url: str, output_dir: str | None = None, mode: str = "tar"):
    owner, repo, branch, path = parse_github_tree_url(url)
    target = output_dir or target_dir_from_url(url, path)
    os.makedirs(target, exist_ok=True)

    token = os.getenv("GITHUB_TOKEN") or None
    print(f"Source: {owner}/{repo}@{branch}/{path or ''}")
    print(f"Target directory: {target}")
    if token:
        print("Using GITHUB_TOKEN for higher rate limits.")
    print(f"Mode: {mode}")

    if mode == "api":
        # Permissions-aware API (Trees+Blobs)
        sync_with_permissions_api(owner, repo, branch, path, target, token=token)
    else:
        # Fast tarball path (recommended)
        download_tarball_and_extract(owner, repo, branch, path, target, token=token)

    print("✅ Done.")


# ---------------------------
# CLI
# ---------------------------


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "Usage: python download_github_tree.py <github-tree-url> [target_dir] [--mode=tar|api]"
        )
        print("Examples:")
        print(
            "  python download_github_tree.py https://github.com/bitnami/containers/tree/main/bitnami/openldap"
        )
        print(
            "  python download_github_tree.py https://github.com/OWNER/REPO/tree/BRANCH/sub/dir outdir --mode=api"
        )
        return 1

    url_arg = argv[1]
    out_arg = None
    mode = "tar"

    # Optional args
    extra = argv[2:]
    if extra:
        # If first extra doesn't look like a flag, treat as output dir
        if not extra[0].startswith("--"):
            out_arg = extra[0]
            extra = extra[1:]

        for a in extra:
            m = re.match(r"--mode=(tar|api)$", a)
            if m:
                mode = m.group(1)
            else:
                print(f"Unknown option: {a}")
                return 2

    download_github_tree(url_arg, out_arg, mode=mode)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
