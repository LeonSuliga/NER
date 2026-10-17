#!/usr/bin/env python3
"""Audit annotation files for Label Studio exports and project span/BIO datasets.

This script checks real annotation datasets and ignores raw JSONL staging files unless
requested explicitly. It supports:
- Label Studio JSON/JSONL exports with `result` / `annotations`
- project-native span datasets like [{'text': ..., 'spans': [...]}]
- BIO token/tag datasets like [{'tokens': [...], 'tags': [...]}]
"""

import argparse
import json
import os
from collections import Counter

DEFAULT_ROOTS = ["data", "staging", "exports", "annotations", "label_studio"]
RAW_DIR_NAMES = {"raw", "staging", "processed", "exports", "annotations", "label_studio", "tmp", "cache"}


def discover_candidate_files(root: str, only_labeled: bool = False):
    files = []
    seen = set()
    bases = [root] + [os.path.join(root, x) for x in DEFAULT_ROOTS]
    for base in bases:
        if not os.path.exists(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [
                d for d in dirnames
                if d not in {".git", ".idea", ".venv", "__pycache__"}
                and (not only_labeled or d.lower() == "labeled" or d.lower() not in RAW_DIR_NAMES)
            ]
            for filename in filenames:
                if not filename.endswith((".json", ".jsonl")) and "." in filename:
                    continue
                full = os.path.join(dirpath, filename)
                if full in seen:
                    continue
                if filename.endswith((".json", ".jsonl")) or "." not in filename:
                    seen.add(full)
                    files.append(full)
    return sorted(files)


def load_json_or_jsonl(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            if path.endswith(".jsonl"):
                rows = []
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
                return rows
            return json.load(fh)
    except Exception:
        return None


def looks_like_project_span_dataset(obj):
    if isinstance(obj, list):
        return bool(obj) and isinstance(obj[0], dict) and "text" in obj[0] and "spans" in obj[0]
    if isinstance(obj, dict):
        return ("text" in obj and "spans" in obj) or (
            "data" in obj and isinstance(obj.get("data"), dict)
            and "text" in obj["data"] and "spans" in obj["data"]
        )
    return False


def looks_like_bio_dataset(obj):
    if isinstance(obj, list):
        return bool(obj) and isinstance(obj[0], dict) and "tokens" in obj[0] and "tags" in obj[0]
    if isinstance(obj, dict):
        return ("tokens" in obj and "tags" in obj) or (
            "data" in obj and isinstance(obj.get("data"), dict)
            and "tokens" in obj["data"] and "tags" in obj["data"]
        )
    return False


def looks_like_label_studio_export(obj):
    if isinstance(obj, list):
        if not obj:
            return False
        return any(isinstance(item, dict) and ("annotations" in item or "tasks" in item or "result" in item) for item in obj)
    if isinstance(obj, dict):
        if any(key in obj for key in ("annotations", "tasks", "result")):
            return True
        if isinstance(obj.get("data"), dict):
            return any(key in obj["data"] for key in ("annotations", "result"))
        return False
    return False


def extract_project_spans(obj):
    docs = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and "text" in item and "spans" in item:
                docs.append({"text": item.get("text", ""), "spans": item.get("spans", [])})
    elif isinstance(obj, dict) and "text" in obj and "spans" in obj:
        docs.append({"text": obj.get("text", ""), "spans": obj.get("spans", [])})
    return docs


def extract_bio_samples(obj):
    samples = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and "tokens" in item and "tags" in item:
                samples.append({"tokens": item.get("tokens", []), "tags": item.get("tags", [])})
    elif isinstance(obj, dict) and "tokens" in obj and "tags" in obj:
        samples.append({"tokens": obj.get("tokens", []), "tags": obj.get("tags", [])})
    return samples


def get_doc_text(task):
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


def extract_label_name(result):
    value = result.get("value") if isinstance(result.get("value"), dict) else {}
    if isinstance(value.get("labels"), list) and value["labels"]:
        return str(value["labels"][0])
    if isinstance(value.get("label"), str):
        return value["label"]
    if isinstance(result.get("from_name"), str):
        return result["from_name"]
    if isinstance(result.get("type"), str):
        return result["type"]
    return "UNKNOWN"


def extract_labelstudio_spans(task):
    spans = []
    result_blocks = []
    if isinstance(task.get("result"), list):
        result_blocks.extend(task["result"])
    if isinstance(task.get("annotations"), list):
        for ann in task["annotations"]:
            if isinstance(ann, dict) and isinstance(ann.get("result"), list):
                result_blocks.extend(ann["result"])
    if isinstance(task.get("data"), dict) and isinstance(task["data"].get("result"), list):
        result_blocks.extend(task["data"]["result"])
    seen = set()
    for result in result_blocks:
        if not isinstance(result, dict):
            continue
        if id(result) in seen:
            continue
        seen.add(id(result))
        value = result.get("value") if isinstance(result.get("value"), dict) else {}
        if "spans" in value and isinstance(value["spans"], list):
            for span in value["spans"]:
                if not isinstance(span, dict):
                    continue
                label = span.get("label") or span.get("labels", [None])[0] or extract_label_name(result)
                start = span.get("start")
                end = span.get("end")
                if start is None or end is None:
                    continue
                spans.append({"label": str(label), "start": int(start), "end": int(end)})
        elif "start" in value and "end" in value:
            label = extract_label_name(result)
            start = value.get("start")
            end = value.get("end")
            if start is None or end is None:
                continue
            spans.append({"label": str(label), "start": int(start), "end": int(end)})
    return spans


def extract_labelstudio_documents(obj):
    out = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and ("annotations" in item or "tasks" in item or "result" in item):
                text = get_doc_text(item)
                spans = extract_labelstudio_spans(item)
                source = item.get("id") or "item"
                out.append((text, spans, str(source)))
    elif isinstance(obj, dict):
        if "annotations" in obj or "tasks" in obj or "result" in obj:
            tasks = obj.get("tasks") if isinstance(obj.get("tasks"), list) else [obj]
            for task in tasks:
                if isinstance(task, dict):
                    text = get_doc_text(task)
                    spans = extract_labelstudio_spans(task)
                    source = task.get("id") or task.get("task_id") or "task"
                    out.append((text, spans, str(source)))
    return out


def get_doc_identifier(doc, fallback=None):
    if not isinstance(doc, dict):
        return str(fallback)
    for key in ("id", "source_act_id", "doc_id", "task_id", "uid"):
        value = doc.get(key)
        if value not in (None, ""):
            return str(value)
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    for key in ("source_act_id", "doc_id", "id"):
        value = meta.get(key)
        if value not in (None, ""):
            return str(value)
    return str(fallback) if fallback is not None else "unknown"


def compute_span_stats(text, spans):
    valid = 0
    invalid = 0
    invalid_reasons = Counter()
    labels = Counter()
    whitespace_issues = 0
    intervals = []

    for sp in spans:
        label = str(sp.get("label", "")).strip()
        start = sp.get("start")
        end = sp.get("end")
        if not label:
            invalid += 1
            invalid_reasons["empty_label"] += 1
            continue
        labels[label] += 1
        try:
            start_i = int(start)
            end_i = int(end)
        except Exception:
            invalid += 1
            invalid_reasons["non_numeric_bounds"] += 1
            continue
        if start_i < 0 or end_i <= start_i:
            invalid += 1
            invalid_reasons["bad_range"] += 1
            continue
        if end_i > len(text):
            invalid += 1
            invalid_reasons["out_of_bounds"] += 1
            continue
        sub = text[start_i:end_i]
        if sub.strip() != sub:
            whitespace_issues += 1
            invalid_reasons["whitespace_edge"] += 1
        intervals.append((start_i, end_i, label))
        valid += 1

    overlaps = 0
    intervals_sorted = sorted(intervals, key=lambda x: (x[0], x[1]))
    for i in range(len(intervals_sorted)):
        s1, e1, _ = intervals_sorted[i]
        for j in range(i + 1, len(intervals_sorted)):
            s2, e2, _ = intervals_sorted[j]
            if s2 < e1 and s1 < e2:
                overlaps += 1
                invalid_reasons["overlap"] += 1
                break

    return {
        "valid": valid,
        "invalid": invalid,
        "overlaps": overlaps,
        "whitespace_issues": whitespace_issues,
        "labels": labels,
        "invalid_reasons": dict(invalid_reasons),
    }


def bio_stats(samples):
    total = len(samples)
    mismatch = 0
    labels = Counter()
    for sample in samples:
        tokens = sample.get("tokens") or []
        tags = sample.get("tags") or []
        if len(tokens) != len(tags):
            mismatch += 1
            continue
        for tag in tags:
            if isinstance(tag, str) and tag != "O":
                labels[tag] += 1
    return {"documents": total, "token_tag_mismatch": mismatch, "label_distribution": dict(labels)}


def summarize_key_value_imbalance(label_counts):
    warnings = []
    for label in sorted(label_counts.keys()):
        if label.endswith("_KEY"):
            base = label[:-4]
            if f"{base}_VAL" not in label_counts:
                warnings.append(f"{label} has no matching {base}_VAL in dataset")
        elif label.endswith("_VAL"):
            base = label[:-4]
            if f"{base}_KEY" not in label_counts:
                warnings.append(f"{label} has no matching {base}_KEY in dataset")
    return warnings


def print_report_for_project_dataset(path, docs, format_name):
    total_docs = len(docs)
    total_spans = sum(len(doc.get("spans", [])) for doc in docs)
    label_counts = Counter()
    invalid_docs = 0
    total_invalid = 0
    total_overlaps = 0
    total_whitespace_issues = 0
    invalid_reasons = Counter()
    overlap_ids = []

    for idx, doc in enumerate(docs):
        text = doc.get("text", "")
        spans = doc.get("spans", [])
        stats = compute_span_stats(text, spans)
        label_counts.update(stats["labels"])
        total_invalid += stats["invalid"]
        total_overlaps += stats["overlaps"]
        total_whitespace_issues += stats["whitespace_issues"]
        invalid_reasons.update(stats["invalid_reasons"])
        doc_id = get_doc_identifier(doc, idx)
        if stats["invalid"] > 0 or stats["overlaps"] > 0:
            invalid_docs += 1
            if stats["overlaps"] > 0:
                overlap_ids.append(doc_id)

    avg_spans = (total_spans / total_docs) if total_docs else 0.0
    valid_spans = total_spans - total_invalid
    print(f"\nFILE: {path}")
    print(f"  format: {format_name}")
    print(f"  docs: {total_docs}")
    print(f"  spans: {total_spans}")
    print(f"  valid spans: {valid_spans}")
    print(f"  invalid spans: {total_invalid}")
    print(f"  docs with invalid spans: {invalid_docs}")
    print(f"  avg spans/doc: {avg_spans:.2f}")
    print(f"  overlap candidates: {total_overlaps}")
    print(f"  whitespace edge issues: {total_whitespace_issues}")
    if overlap_ids:
        print(f"  overlapping document IDs: {', '.join(map(str, overlap_ids))}")
    else:
        print("  overlapping document IDs: none")
    if label_counts:
        print("  label distribution:")
        for label, count in sorted(label_counts.items()):
            print(f"    - {label}: {count}")
    if invalid_reasons:
        print("  invalid reasons:")
        for reason, count in sorted(invalid_reasons.items()):
            print(f"    - {reason}: {count}")
    warnings = summarize_key_value_imbalance(label_counts)
    if warnings:
        print("  key/value warnings:")
        for warn in warnings:
            print(f"    - {warn}")
    else:
        print("  key/value warnings: none")


def _aggregate_labelstudio_docs(docs):
    total_docs = len(docs)
    total_spans = sum(len(spans) for _, spans, _ in docs)
    label_counts = Counter()
    invalid_total = 0
    invalid_docs = 0
    overlap_total = 0
    whitespace_total = 0
    invalid_reasons = Counter()
    overlap_ids = []
    overlap_details = []
    missing_text_docs = 0
    offset_validation_skipped = 0

    for idx, (text, spans, source) in enumerate(docs):
        for span in spans:
            label = str(span.get("label", "")).strip()
            if label:
                label_counts[label] += 1
        if not text:
            missing_text_docs += 1
            offset_validation_skipped += 1
            continue
        stats = compute_span_stats(text, spans)
        label_counts.update(stats["labels"])
        invalid_total += stats["invalid"]
        overlap_total += stats["overlaps"]
        whitespace_total += stats["whitespace_issues"]
        invalid_reasons.update(stats["invalid_reasons"])
        if stats["invalid"] > 0 or stats["overlaps"] > 0:
            invalid_docs += 1
            if stats["overlaps"] > 0:
                overlap_ids.append(str(source) if source else f"row_{idx}")
                overlap_details.append({
                    "source": str(source) if source else f"row_{idx}",
                    "spans": spans,
                    "text_length": len(text),
                    "overlap_count": stats["overlaps"],
                })

    return {
        "docs": total_docs,
        "spans": total_spans,
        "invalid_spans": invalid_total,
        "avg_spans_per_doc": (total_spans / total_docs) if total_docs else 0.0,
        "docs_with_bad_spans": invalid_docs,
        "overlap_candidates": overlap_total,
        "whitespace_edge_issues": whitespace_total,
        "missing_text_docs": missing_text_docs,
        "offset_validation_skipped": offset_validation_skipped,
        "label_counts": label_counts,
        "invalid_reasons": invalid_reasons,
        "overlap_ids": overlap_ids,
        "overlap_details": overlap_details,
    }


def print_report_for_labelstudio(path, docs):
    summary = _aggregate_labelstudio_docs(docs)
    label_counts = summary["label_counts"]
    invalid_reasons = summary["invalid_reasons"]
    avg_spans = summary["avg_spans_per_doc"]

    print(f"\nFILE: {path}")
    print("  format: Label Studio export")
    print(f"  docs: {summary['docs']}")
    print(f"  spans: {summary['spans']}")
    print(f"  offset validation: skipped ({summary['offset_validation_skipped']} docs missing original text)")
    print(f"  invalid spans: {summary['invalid_spans']}")
    print(f"  avg spans/doc: {avg_spans:.2f}")
    print(f"  docs with bad spans: {summary['docs_with_bad_spans']}")
    print(f"  overlap candidates: {summary['overlap_candidates']}")
    print(f"  whitespace edge issues: {summary['whitespace_edge_issues']}")
    if summary["missing_text_docs"]:
        print(f"  docs without source text (cannot validate offsets): {summary['missing_text_docs']}")
    if summary["overlap_ids"]:
        print(f"  overlapping document IDs: {', '.join(summary['overlap_ids'])}")
    else:
        print("  overlapping document IDs: none")
    if label_counts:
        print("  label distribution:")
        for label, count in sorted(label_counts.items()):
            print(f"    - {label}: {count}")
    if invalid_reasons:
        print("  invalid reasons:")
        for reason, count in sorted(invalid_reasons.items()):
            print(f"    - {reason}: {count}")
    warnings = summarize_key_value_imbalance(label_counts)
    print("  key/value warnings:")
    if warnings:
        for warn in warnings:
            print(f"    - {warn}")
    else:
        print("    - none")


def print_aggregate_labelstudio_summary(ls_files):
    aggregated_docs = []
    for _, docs in ls_files:
        aggregated_docs.extend(docs)
    summary = _aggregate_labelstudio_docs(aggregated_docs)
    label_counts = summary["label_counts"]
    invalid_reasons = summary["invalid_reasons"]

    print("\n=== Aggregated Label Studio summary ===")
    print(f"Files: {len(ls_files)}")
    print(f"Total docs: {summary['docs']}")
    print(f"Total spans: {summary['spans']}")
    print(f"Offset validation skipped: {summary['offset_validation_skipped']} docs without source text")
    print(f"Invalid spans: {summary['invalid_spans']}")
    print(f"Avg spans/doc: {summary['avg_spans_per_doc']:.2f}")
    print(f"Docs with bad spans: {summary['docs_with_bad_spans']}")
    print(f"Overlap candidates: {summary['overlap_candidates']}")
    print(f"Whitespace edge issues: {summary['whitespace_edge_issues']}")
    if summary["overlap_ids"]:
        print(f"Overlapping doc IDs: {', '.join(summary['overlap_ids'])}")
        print("Overlap details:")
        for item in summary["overlap_details"]:
            source = item["source"]
            spans = item["spans"]
            print(f"  - {source}: {len(spans)} spans, overlap_count={item['overlap_count']}")
            for span in spans[:10]:
                print(f"      * {span.get('label')}: {span.get('start')}..{span.get('end')}")
            if len(spans) > 10:
                print(f"      * ... and {len(spans)-10} more spans")
    else:
        print("Overlapping doc IDs: none")
    print("Label distribution:")
    for label, count in sorted(label_counts.items()):
        print(f"  - {label}: {count}")
    if invalid_reasons:
        print("Invalid reasons:")
        for reason, count in sorted(invalid_reasons.items()):
            print(f"  - {reason}: {count}")
    warnings = summarize_key_value_imbalance(label_counts)
    print("Key/value warnings:")
    if warnings:
        for warn in warnings:
            print(f"  - {warn}")
    else:
        print("  - none")


def analyze_path(path):
    obj = load_json_or_jsonl(path)
    if obj is None:
        return {"type": "unreadable", "path": path}
    if looks_like_project_span_dataset(obj):
        return {"type": "project_span", "docs": extract_project_spans(obj), "path": path}
    if looks_like_bio_dataset(obj):
        return {"type": "bio", "path": path, "stats": bio_stats(extract_bio_samples(obj))}
    if looks_like_label_studio_export(obj):
        return {"type": "label_studio", "docs": extract_labelstudio_documents(obj), "path": path}
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        return {"type": "raw_records", "path": path, "count": len(obj)}
    return {"type": "unknown", "path": path}


def main():
    parser = argparse.ArgumentParser(description="Audit annotation data quality and Label Studio exports.")
    parser.add_argument("--root", default=".", help="Project root to scan for annotation files")
    parser.add_argument("--only-labeled", action="store_true", help="Skip raw/unannotated files and only audit labeled datasets.")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    candidates = discover_candidate_files(root, only_labeled=args.only_labeled)

    print("=== Annotation Audit ===")
    print(f"Project root: {root}")
    print(f"Candidate files: {len(candidates)}")
    if args.only_labeled:
        print("Mode: only labeled datasets (raw/unannotated files skipped)")

    if not candidates:
        print("No JSON/JSONL files found under root. Nothing to audit.")
        return

    project_span_files = []
    bio_files = []
    ls_files = []
    raw_files = []
    unknown_files = []

    for path in candidates:
        info = analyze_path(path)
        typ = info.get("type")
        if typ == "project_span":
            project_span_files.append((path, info["docs"]))
        elif typ == "bio":
            bio_files.append((path, info["stats"]))
        elif typ == "label_studio":
            ls_files.append((path, info["docs"]))
        elif typ == "raw_records":
            raw_files.append(path)
        else:
            unknown_files.append(path)

    if project_span_files:
        print("\nDetected project-style span datasets:")
        for path, docs in project_span_files:
            print_report_for_project_dataset(path, docs, "project_span")

    if bio_files:
        print("\nDetected BIO token datasets:")
        for path, stats in bio_files:
            print(f"\nFILE: {path}")
            print(f"  docs: {stats['documents']}")
            print(f"  token/tag mismatches: {stats['token_tag_mismatch']}")
            print("  label distribution:")
            for label, count in sorted(stats["label_distribution"].items()):
                print(f"    - {label}: {count}")

    if ls_files:
        print_aggregate_labelstudio_summary(ls_files)

    if raw_files and not args.only_labeled:
        print("\nLikely raw/unannotated JSON/JSONL files:")
        for path in raw_files:
            print(f"  - {path}")

    if unknown_files and not args.only_labeled:
        print("\nUnknown file types (not recognized as BIO/span/LS):")
        for path in unknown_files:
            print(f"  - {path}")

    if args.only_labeled:
        print("\nSanitization/audit was applied only to labeled annotation datasets; raw files were skipped.")

    print("\n=== Integration check with convert_dataset.py ===")
    print("convert_dataset.py expects project-native records shaped like:")
    print("  [{'text': '...', 'spans': [{'label': 'LAW_TITLE', 'start': 10, 'end': 50}, ...]}]")
    print("If the upstream export is from Label Studio, it usually requires an adapter because Label Studio stores spans under")
    print("  annotations[i].result[j].value.start / end / labels")
    print("rather than under a flat 'spans' list. The adapter is only needed for raw Label Studio exports.")
    print("The repo's existing data/ner_dataset.json already matches the convert_dataset.py contract without a custom adapter.")


if __name__ == "__main__":
    main()
