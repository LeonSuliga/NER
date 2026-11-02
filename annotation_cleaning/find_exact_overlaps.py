#!/usr/bin/env python3
"""Print exact overlapping span pairs in the labeled Label Studio files."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "data_prep"))
from labeled_files import display_name, iter_labeled_files  # noqa: E402


def load_doc(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def extract_spans(task):
    spans = []
    for result in task.get("result", []):
        value = result.get("value", {})
        labels = value.get("labels") or []
        if "start" in value and "end" in value and labels:
            spans.append({
                "label": labels[0],
                "start": int(value["start"]),
                "end": int(value["end"]),
                "text": value.get("text", ""),
            })
    return spans


def find_overlaps(spans):
    overlaps = []
    ordered = sorted(spans, key=lambda s: (s["start"], s["end"]))
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            cur = ordered[i]
            nxt = ordered[j]
            if cur["end"] > nxt["start"] and cur["start"] < nxt["end"]:
                overlaps.append((cur, nxt))
    return overlaps


total_overlap_files = 0
total_overlap_pairs = 0

for path in iter_labeled_files():
    task = load_doc(path)
    text = task.get("task", {}).get("data", {}).get("text")
    if text is None:
        text = task.get("data", {}).get("text")
    spans = extract_spans(task)
    overlaps = find_overlaps(spans)

    print(f"\n=== FILE: {display_name(path)} ===")
    print(f"Document text length: {len(text) if text is not None else 'N/A'}")
    print(f"Total spans: {len(spans)}")
    print(f"Overlap pairs: {len(overlaps)}")

    if not overlaps:
        print("No overlaps found.")
        continue

    total_overlap_files += 1
    total_overlap_pairs += len(overlaps)

    for prev, nxt in overlaps:
        print(
            "OVERLAP: "
            f"prev={prev['label']} start={prev['start']} end={prev['end']} text={prev['text']!r} | "
            f"next={nxt['label']} start={nxt['start']} end={nxt['end']} text={nxt['text']!r}"
        )

        if text is not None:
            prev_snip = text[max(0, prev['start'] - 25): min(len(text), prev['end'] + 25)]
            nxt_snip = text[max(0, nxt['start'] - 25): min(len(text), nxt['end'] + 25)]
            def safe_ascii(s):
                return s.encode('ascii', errors='replace').decode('ascii')
            print("  prev context: " + safe_ascii(prev_snip))
            print("  next context: " + safe_ascii(nxt_snip))

print(f"\n=== SUMMARY ===")
print(f"Files with overlaps: {total_overlap_files}")
print(f"Total overlap pairs: {total_overlap_pairs}")
