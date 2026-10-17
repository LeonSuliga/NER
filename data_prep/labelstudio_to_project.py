#!/usr/bin/env python3
"""Convert cleaned Label Studio exports in data/labeled/ into project-native span format."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABELED_DIR = PROJECT_ROOT / "data" / "labeled"
OUTPUT_PATH = PROJECT_ROOT / "data" / "ner_dataset.json"


def get_text(task):
    if not isinstance(task, dict):
        return ""

    def walk(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("text"), str):
                return obj["text"]
            if isinstance(obj.get("data"), dict):
                result = walk(obj["data"])
                if result:
                    return result
            if isinstance(obj.get("task"), dict):
                result = walk(obj["task"])
                if result:
                    return result
            for value in obj.values():
                result = walk(value)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = walk(item)
                if result:
                    return result
        return ""

    return walk(task)


def extract_spans(task):
    spans = []
    results = task.get("result") if isinstance(task.get("result"), list) else []
    seen = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        value = result.get("value") if isinstance(result.get("value"), dict) else {}
        labels = value.get("labels") or []
        start = value.get("start")
        end = value.get("end")
        if not labels or start is None or end is None:
            continue
        label = labels[0]
        start_i = int(start)
        end_i = int(end)
        key = (start_i, end_i, label)
        if key in seen:
            continue
        seen.add(key)
        spans.append({"label": str(label), "start": start_i, "end": end_i})
    return spans


def main():
    files = sorted(LABELED_DIR.iterdir(), key=lambda p: p.name)
    samples = []

    for path in files:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                obj = json.load(fh)
        except Exception:
            continue

        text = get_text(obj)
        if not text:
            continue
        spans = extract_spans(obj)
        sample = {
            "text": text,
            "spans": spans,
            "meta": {"source_file": path.name},
        }
        samples.append(sample)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(samples, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"Converted {len(samples)} labeled files to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
