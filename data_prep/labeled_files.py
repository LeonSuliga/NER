"""Locate the current hand-labeled Label Studio files under data/labeled/part*/."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABELED_DIR = PROJECT_ROOT / "data" / "labeled"


def iter_labeled_files():
    """Yield the labeled files of every data/labeled/part*/ folder.

    A part that has an after_check/ subfolder (re-checked labels) is read from there instead of
    its top-level files; to_check/ only holds copies prepared for re-import and is skipped.
    """
    if not LABELED_DIR.exists():
        return
    for part in sorted(p for p in LABELED_DIR.iterdir() if p.is_dir() and p.name.startswith("part")):
        source = part / "after_check" if (part / "after_check").is_dir() else part
        yield from sorted((p for p in source.iterdir() if p.is_file() and p.name != ".DS_Store"),
                          key=lambda p: p.name)


def display_name(path):
    """Path relative to data/labeled/, e.g. 'part3/after_check/12' (file names repeat across parts)."""
    return Path(path).relative_to(LABELED_DIR).as_posix()
