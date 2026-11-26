"""Documents MCP server - read-only access to local documents."""

from pathlib import Path

# Default documents directory (can be overridden via environment)
DOCS_DIR = Path(__file__).parent.parent.parent.parent / "demo_data" / "documents"


def list_files() -> list[dict[str, str]]:
    """List all document files available.

    Returns:
        List of files with name and path information.
    """
    if not DOCS_DIR.exists():
        return []

    files = []
    for file_path in DOCS_DIR.glob("*"):
        if file_path.is_file():
            files.append({"name": file_path.name, "path": str(file_path.relative_to(DOCS_DIR))})

    return files


def read_text(filename: str) -> str:
    """Read the contents of a text document.

    Args:
        filename: Name of the file to read (e.g., 'report.md' or 'notes.txt').
                  Placeholders like [PERSON_1] are accepted in the filename.

    Returns:
        The full text content of the document.
    """
    file_path = DOCS_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Document not found: {filename}")

    if not file_path.is_relative_to(DOCS_DIR):
        raise ValueError("Invalid file path - must be within documents directory")

    return file_path.read_text(encoding="utf-8")


def search_files(query: str) -> list[dict[str, str]]:
    """Search for documents containing specific text.

    Args:
        query: Text to search for in document contents.
               Placeholders like [PERSON_1] are accepted.

    Returns:
        List of matching files with excerpts.
    """
    if not DOCS_DIR.exists():
        return []

    matches = []
    for file_path in DOCS_DIR.glob("*"):
        if file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8")
                if query.lower() in content.lower():
                    # Extract context around the match
                    lines = content.split("\n")
                    matching_lines = [line for line in lines if query.lower() in line.lower()]
                    excerpt = "\n".join(matching_lines[:3])  # First 3 matching lines

                    matches.append(
                        {
                            "name": file_path.name,
                            "path": str(file_path.relative_to(DOCS_DIR)),
                            "excerpt": excerpt[:200],  # Limit excerpt length
                        }
                    )
            except (UnicodeDecodeError, OSError):
                continue  # Skip files that can't be read as text

    return matches
