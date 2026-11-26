"""Notes MCP server - read-only access to personal notes."""

from pathlib import Path

# Default notes directory
NOTES_DIR = Path(__file__).parent.parent.parent.parent / "demo_data" / "notes"


def search_notes(query: str) -> list[dict[str, str]]:
    """Search for notes containing specific text.

    Args:
        query: Text to search for in note contents. Placeholders like [PERSON_1] are accepted.

    Returns:
        List of matching notes with excerpts.
    """
    if not NOTES_DIR.exists():
        return []

    matches = []
    for note_file in NOTES_DIR.glob("*.md"):
        try:
            content = note_file.read_text(encoding="utf-8")
            if query.lower() in content.lower():
                # Extract context around match
                lines = content.split("\n")
                matching_lines = [line for line in lines if query.lower() in line.lower()]
                excerpt = "\n".join(matching_lines[:3])

                matches.append(
                    {
                        "name": note_file.name,
                        "excerpt": excerpt[:200],
                        "path": str(note_file.relative_to(NOTES_DIR)),
                    }
                )
        except (UnicodeDecodeError, OSError):
            continue

    return matches


def read_note(filename: str) -> str:
    """Read the contents of a specific note file.

    Args:
        filename: Name of the note file to read. Placeholders like [PERSON_1] are accepted.

    Returns:
        The full text content of the note.
    """
    note_file = NOTES_DIR / filename
    if not note_file.exists():
        raise FileNotFoundError(f"Note not found: {filename}")

    if not note_file.is_relative_to(NOTES_DIR):
        raise ValueError("Invalid file path - must be within notes directory")

    return note_file.read_text(encoding="utf-8")


def list_notes() -> list[dict[str, str]]:
    """List all available notes.

    Returns:
        List of note files with name and path information.
    """
    if not NOTES_DIR.exists():
        return []

    notes = []
    for note_file in NOTES_DIR.glob("*.md"):
        if note_file.is_file():
            notes.append({"name": note_file.name, "path": str(note_file.relative_to(NOTES_DIR))})

    return notes
