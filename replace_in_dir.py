import os


def replace_in_file(file_path: str, replacements: list[tuple[str, str]]) -> None:
    """Replaces multiple string pairs in a single file.

    Args:
        file_path: Path to the file to modify.
        replacements: List of (old_str, new_str) pairs.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content: str = f.read()

            modified = False
            for old_str, new_str in replacements:
                if old_str in content:
                    content = content.replace(old_str, new_str)
                    modified = True

            if modified:
                with open(file_path, "w", encoding="utf-8") as f:
                    _ = f.write(content)
                print(f"Replaced in: {file_path}")

    except (UnicodeDecodeError, PermissionError, IsADirectoryError):
        # Skip binary or unreadable files
        pass


def replace_in_directory(
    directory: str,
    replacements: list[tuple[str, str]],
    file_extension: str | None = None,
) -> None:
    """Recursively performs multiple string replacements in all files under directory.

    Args:
        directory: Root directory to search in.
        replacements: List of (old_str, new_str) pairs.
        file_extension: Optional file extension filter (e.g., '.txt', '.py').
    """
    for root, _, files in os.walk(directory):
        for file_name in files:
            if file_extension and not file_name.endswith(file_extension):
                continue
            file_path = os.path.join(root, file_name)
            replace_in_file(file_path, replacements)
