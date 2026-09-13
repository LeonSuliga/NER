import glob
import json
import os
import spacy
from spacy.tokens import DocBin

nlp = spacy.blank('pl')
db_train, db_val = DocBin(), DocBin()

labeled_files = sorted(
    glob.glob('data/labeled/[0-9]*'),
    key=lambda x: int(os.path.basename(x)),
)

split_idx = int(len(labeled_files) * 0.8)

for i, fpath in enumerate(labeled_files):
  try:
    with open(fpath, 'r', encoding='utf-8') as f:
      task = json.load(f)

    text = task.get('data', {}).get('text', '')
    if not text:
      continue

    doc = nlp.make_doc(text)
    ents = []
    for r in task.get('result', []):
      val = r.get('value', {})
      if 'start' in val and 'end' in val and 'labels' in val:
        span = doc.char_span(
            val['start'],
            val['end'],
            label=val['labels'][0],
            alignment_mode='contract',
        )
        if span:
          ents.append(span)

    doc.ents = ents
    if i < split_idx:
      db_train.add(doc)
    else:
      db_val.add(doc)
  except Exception as e:
    print(f'Błąd w {fpath}: {e}')

os.makedirs('data/spacy_direct', exist_ok=True)
db_train.to_disk('data/spacy_direct/train.spacy')
db_val.to_disk('data/spacy_direct/dev.spacy')
print(
    f'Zapisano {split_idx} doc w train.spacy, {len(labeled_files)-split_idx} doc'
    ' w dev.spacy.'
)