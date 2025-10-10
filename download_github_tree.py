#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "github-recursive-downloader/1.0 (+https://example.local)"


def parse_github_tree_url(url: str) -> tuple[str, str, str, str]:
    """
    Parse a GitHub tree URL like:
      https://github.com/{owner}/{repo}/tree/{branch}/{path...}
    Returns (owner, repo, branch, path)
    Path may be "" for the repo root at that branch.
    """
    parsed = urllib.parse.urlparse(url)
    parts = parsed.path.strip("/").split("/")
    # Expect ... / owner / repo / tree / branch / [path...]
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


def github_api_request(url: str, token: str | None = None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_file(raw_url: str, dest_path: str, token: str | None = None):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    headers = {"User-Agent": USER_AGENT}
    # Prefer direct download_url (raw content). If a token is present, we can still use it for higher limits.
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(raw_url, headers=headers)
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out:
        out.write(resp.read())


def sync_directory(
    owner: str,
    repo: str,
    branch: str,
    path: str,
    out_dir: str,
    token: str | None = None,
):
    """
    Recursively sync a directory from GitHub to out_dir using the Contents API.
    API: https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}
    """
    api_base = f"https://api.github.com/repos/{owner}/{repo}/contents"
    encoded_path = urllib.parse.quote(path) if path else ""
    api_url = f"{api_base}/{encoded_path}" if encoded_path else api_base
    api_url += f"?ref={urllib.parse.quote(branch)}"

    try:
        items = github_api_request(api_url, token=token)
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"GitHub API error {e.code} for {api_url}: {e.read().decode(errors='ignore')}"
        ) from e

    if isinstance(items, dict) and items.get("type") == "file":
        # Single file response (rare when path points directly to a file)
        rel_path = items["name"]
        dest = os.path.join(out_dir, rel_path)
        print(f"Downloading file: {rel_path}")
        download_file(items["download_url"], dest, token=token)
        return

    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected API response for {api_url}: {items!r}")

    for entry in items:
        etype = entry.get("type")
        name = entry.get("name")
        if not name:
            continue

        if etype == "file":
            rel = name
            dest = os.path.join(out_dir, rel)
            print(f"Downloading file: {os.path.relpath(dest, out_dir)}")
            download_file(entry["download_url"], dest, token=token)

        elif etype == "dir":
            sub_path = f"{path}/{name}" if path else name
            sub_out = os.path.join(out_dir, name)
            os.makedirs(sub_out, exist_ok=True)
            sync_directory(owner, repo, branch, sub_path, sub_out, token=token)

        elif etype in ("symlink", "submodule"):
            # Best-effort: for symlink with a download_url we download the target;
            # submodules don't have content here, so we skip them.
            dl = entry.get("download_url")
            if dl:
                dest = os.path.join(out_dir, name)
                print(
                    f"Downloading symlink target as file: {os.path.relpath(dest, out_dir)}"
                )
                download_file(dl, dest, token=token)
            else:
                print(f"Skipping {etype}: {name}")
        else:
            print(f"Skipping unsupported type '{etype}': {name}")


def download_github_tree(url: str, output_dir: str | None = None):
    owner, repo, branch, path = parse_github_tree_url(url)
    target = output_dir or target_dir_from_url(url, path)
    os.makedirs(target, exist_ok=True)

    token = os.getenv("GITHUB_TOKEN") or None
    print(f"Source: {owner}/{repo}@{branch}/{path or ''}")
    print(f"Target directory: {target}")
    if token:
        print("Using GITHUB_TOKEN for higher rate limits.")

    sync_directory(owner, repo, branch, path, target, token=token)
    print("✅ Done.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_github_tree.py <github-tree-url> [target_dir]")
        print("Example:")
        print(
            "  python download_github_tree.py https://github.com/bitnami/containers/tree/main/bitnami/openldap"
        )
        sys.exit(1)

    url_arg = sys.argv[1]
    out_arg = sys.argv[2] if len(sys.argv) >= 3 else None
    download_github_tree(url_arg, out_arg)
