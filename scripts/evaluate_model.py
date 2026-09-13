from pathlib import Path

import spacy
from spacy.scorer import Scorer
from spacy.tokens import DocBin
from spacy.training import Example

ROOT = Path(__file__).resolve().parents[1]

model_candidates = [
    ROOT / 'models' / 'ner_spacy',
    ROOT / 'models' / 'ner_spacy' / 'model-best',
    ROOT / 'models' / 'ner_spacy' / 'model-last',
    Path('./models/ner_spacy'),
]
model_path = next((p for p in model_candidates if p.exists()), model_candidates[0])

# Prefer the project split under data/spacy; fall back to data/test.spacy
test_candidates = [
    ROOT / 'data' / 'spacy' / 'test.spacy',
    ROOT / 'data' / 'test.spacy',
    Path('./data/spacy/test.spacy'),
    Path('./data/test.spacy'),
]
test_path = next((p for p in test_candidates if p.exists()), test_candidates[0])

print(f'Loading model from: {model_path}')
print(f'Loading test data from: {test_path}')

nlp = spacy.load(str(model_path))
db = DocBin().from_disk(str(test_path))
docs = list(db.get_docs(nlp.vocab))
examples = []

for doc in docs:
    pred = nlp(doc.text)
    examples.append(Example(pred, doc))

scorer = Scorer()
metrics = scorer.score(examples)

print('OVERALL')
print({
    'ents_p': metrics.get('ents_p'),
    'ents_r': metrics.get('ents_r'),
    'ents_f': metrics.get('ents_f'),
})
print('PER_TYPE')
print(metrics.get('ents_per_type', {}))
