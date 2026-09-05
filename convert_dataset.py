import os, json, re
from typing import List, Dict

IN = os.path.join(os.path.dirname(__file__), 'data', 'ner_dataset.json')
OUT = os.path.join(os.path.dirname(__file__), 'data', 'train_bio.json')

# simple tokenizer: split on whitespace and keep punctuation as separate tokens
TOKEN_RE = re.compile(r"\w+|[^	\w\s]", re.UNICODE)

with open(IN, 'r', encoding='utf-8') as fh:
    samples = json.load(fh)

# Convert nested span annotations into BIO labels token by token.
out_samples = []
for s in samples:
    text = s.get('text','')
    spans = s.get('spans', [])
    # build char->label map (we will prefer longest span if overlaps)
    label_map = [None] * len(text)
    for sp in spans:
        lab = sp['label']
        st = sp['start']
        ed = sp['end']
        if st < 0 or ed > len(text):
            continue
        for i in range(st, ed):
            label_map[i] = lab
    # tokenize with offsets
    tokens = []
    tags = []
    for m in TOKEN_RE.finditer(text):
        tok = m.group(0)
        st = m.start()
        ed = m.end()
        tokens.append(tok)
        # determine tag by checking label_map in token span
        sub_labels = [label_map[i] for i in range(st, ed) if i < len(label_map) and label_map[i] is not None]
        if not sub_labels:
            tags.append('O')
        else:
            # prefer most common label in token span
            lab = max(set(sub_labels), key=sub_labels.count)
            # determine B/I
            # if previous token tag had same label and was B/I, then I- else B-
            prev_tag = tags[-1] if tags else 'O'
            prev_lab = prev_tag.split('-',1)[1] if '-' in prev_tag else None
            if prev_lab == lab and prev_tag != 'O':
                tags.append('I-'+lab)
            else:
                tags.append('B-'+lab)
    out_samples.append({'tokens': tokens, 'tags': tags, 'meta': s.get('meta', {})})

# save
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump(out_samples, fh, ensure_ascii=False, indent=2)

print('Converted', len(out_samples), 'samples ->', OUT)
# print first 5 with UTF-8-safe output
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
for ex in out_samples[:5]:
    print('TOKS:', ex['tokens'])
    print('TAGS:', ex['tags'])
    print('---')
