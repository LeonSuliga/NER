#!/usr/bin/env python3
"""Remove overlapping LIT_VAL spans from specific Label Studio files."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABELED_DIR = PROJECT_ROOT / "data" / "labeled"
TARGET_FILES = {"5", "6", "38"}


def extract_span_entry(result):
    if not isinstance(result, dict):
        return None
    value = result.get("value")
    if not isinstance(value, dict):
        return None
    labels = value.get("labels") or []
    if not labels:
        return None
    start = value.get("start")
    end = value.get("end")
    if start is None or end is None:
        return None
    return {
        "idx": None,
        "label": labels[0],
        "start": int(start),
        "end": int(end),
        "text": value.get("text", ""),
    }


def clean_file(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        obj = json.load(fh)
    results = obj.get("result")
    if not isinstance(results, list):
        return 0

    entries = []
    for idx, result in enumerate(results):
        parsed = extract_span_entry(result)
        if parsed is None:
            continue
        parsed["idx"] = idx
        entries.append(parsed)

    to_remove = set()
    for i in range(len(entries)):
        a = entries[i]
        for j in range(i + 1, len(entries)):
            b = entries[j]
            if a["start"] < b["end"] and b["start"] < a["end"]:
                if a["label"] == "LIT_VAL" or b["label"] == "LIT_VAL":
                    to_remove.add(a["idx"])
                    to_remove.add(b["idx"])

    kept = []
    removed = 0
    for idx, result in enumerate(results):
        if idx in to_remove:
            removed += 1
            continue
        kept.append(result)

    obj["result"] = kept
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return removed


def main():
    total_removed = 0
    for name in sorted(TARGET_FILES):
        path = LABELED_DIR / name
        if not path.exists():
            print(f"MISSING: {path}")
            continue
        removed = clean_file(path)
        total_removed += removed
        print(f"{path.name}: removed {removed} overlapping LIT_VAL spans")
    print(f"Total removed: {total_removed}")
    print("Done. Run: python .\\scripts\\audit_annotations.py --root . --only-labeled")


if __name__ == "__main__":
    main()
