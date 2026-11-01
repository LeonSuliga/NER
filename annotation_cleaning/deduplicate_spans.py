#!/usr/bin/env python3
"""Remove duplicate Label Studio spans from files in data/labeled/part*/."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "data_prep"))
from labeled_files import display_name, iter_labeled_files  # noqa: E402


def deduplicate_results(obj):
    if not isinstance(obj, dict):
        return obj, 0

    results = obj.get("result")
    if not isinstance(results, list):
        return obj, 0

    seen = set()
    unique = []
    removed = 0

    for item in results:
        if not isinstance(item, dict):
            unique.append(item)
            continue

        value = item.get("value") if isinstance(item.get("value"), dict) else {}
        start = value.get("start")
        end = value.get("end")
        label = value.get("labels")

        # Deduplicate by (start, end). Allow label in key as well to avoid collisions if different labels share same bounds.
        key = (start, end, tuple(label) if isinstance(label, list) else label)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        unique.append(item)

    obj["result"] = unique
    return obj, removed


def process_file(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        obj = json.load(fh)

    cleaned, removed = deduplicate_results(obj)
    if not removed:
        return 0

    with path.open("w", encoding="utf-8") as fh:
        json.dump(cleaned, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    return removed


def main():
    files = list(iter_labeled_files())
    if not files:
        print("No labeled files found in data/labeled/part*/")
        return

    total_removed = 0
    print("Deduplicating Label Studio spans...")
    for path in files:
        removed = process_file(path)
        total_removed += removed
        print(f"{display_name(path)}: removed {removed} duplicate spans")

    print(f"Total duplicate spans removed: {total_removed}")
    print("Done.")
    print("Next: python .\\annotation_cleaning\\audit_annotations.py --root . --only-labeled")


if __name__ == "__main__":
    main()
