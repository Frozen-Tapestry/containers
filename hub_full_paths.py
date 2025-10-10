import os
import re


def fix_dockerfile_path(dockerfile_path: str) -> None:
    """
    Reads a Dockerfile and ensures FROM lines have a full Docker Hub path.
    Example: FROM caddy:2.10.2 -> FROM docker.io/library/caddy:2.10.2
    Leaves special base images like 'scratch' untouched.
    """
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        lines: list[str] = f.readlines()

    updated_lines: list[str] = []
    changed: bool = False

    for line in lines:
        match = re.match(r"^\s*FROM\s+(\S+)", line)
        if match:
            image: str = match.group(1)
            # Skip special base images or already qualified ones
            if (
                image == "scratch"
                or re.match(r"^[\w\-.]+/[\w\-.]+/", image)
                or image.startswith("docker.io/")
            ):
                updated_lines.append(line)
                continue

            # If image has no namespace (e.g., caddy, alpine), add docker.io/library/
            if "/" not in image.split(":")[0]:
                new_image: str = f"docker.io/library/{image}"
            else:
                new_image = f"docker.io/{image}"

            line = line.replace(image, new_image)
            changed = True

        updated_lines.append(line)

    if changed:
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        print(f"✅ Updated: {dockerfile_path}")
    else:
        print(f"✔ No change needed: {dockerfile_path}")


def find_and_fix_dockerfiles(root: str = ".") -> None:
    """
    Recursively find all Dockerfiles and fix their FROM paths.
    """
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename == "Dockerfile":
                dockerfile_path: str = os.path.join(dirpath, filename)
                fix_dockerfile_path(dockerfile_path)


if __name__ == "__main__":
    print("🔍 Scanning for Dockerfiles...")
    find_and_fix_dockerfiles(".")
    print("✅ Done.")
