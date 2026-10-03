"""Compare the NER models on the same test split.

Every model tags the gold tokenization of data/spacy/test.spacy, and all predictions are scored
with spaCy's span scorer, so P/R/F are directly comparable. Missing models are skipped.

Models:
  spacy_blank    models/ner_spacy                       (train_spacy_ner.py)
  spacy_vectors  models/ner_spacy_vectors/model-best    (train_spacy_vectors.py)
  herbert        models/ner_herbert                     (train_herbert_ner.py)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import spacy
from spacy.scorer import Scorer
from spacy.tokens import Doc, DocBin, Span
from spacy.training import Example

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODELS = {
    'spacy_blank': ('spacy', ROOT / 'models' / 'ner_spacy'),
    'spacy_vectors': ('spacy', ROOT / 'models' / 'ner_spacy_vectors' / 'model-best'),
    'herbert': ('herbert', ROOT / 'models' / 'ner_herbert'),
}


def spacy_predictor(path):
    nlp = spacy.load(path)

    def predict(words, spaces):
        doc = nlp(Doc(nlp.vocab, words=words, spaces=spaces))
        return [(e.start, e.end, e.label_) for e in doc.ents]
    return predict


def herbert_predictor(path):
    from train_herbert_ner import HerbertTagger
    tagger = HerbertTagger.load(str(path))
    return lambda words, spaces: tagger.predict_spans(words)


def evaluate(predict, gold_docs):
    examples = []
    n_tokens = sum(len(d) for d in gold_docs)
    t0 = time.perf_counter()
    for gold in gold_docs:
        words = [t.text for t in gold]
        spaces = [bool(t.whitespace_) for t in gold]
        pred = Doc(gold.vocab, words=words, spaces=spaces)
        pred.ents = spacy.util.filter_spans([Span(pred, s, e, label=l) for s, e, l in predict(words, spaces)])
        examples.append(Example(pred, gold))
    elapsed = time.perf_counter() - t0
    scores = Scorer.score_spans(examples, 'ents')
    scores['tokens_per_sec'] = n_tokens / elapsed if elapsed else None
    return scores


def fmt(x):
    return '  -   ' if x is None else f'{x:.4f}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test', default=str(ROOT / 'data' / 'spacy' / 'test.spacy'))
    ap.add_argument('--out', default=str(ROOT / 'models' / 'comparison.json'))
    args = ap.parse_args()

    gold_docs = list(DocBin().from_disk(args.test).get_docs(spacy.blank('pl').vocab))
    n_ents = sum(len(d.ents) for d in gold_docs)
    print(f'Test set: {args.test} ({len(gold_docs)} docs, {sum(len(d) for d in gold_docs)} tokens, {n_ents} entities)\n')

    results = {}
    for name, (kind, path) in MODELS.items():
        if not path.exists():
            print(f'[skip] {name}: {path} not found')
            continue
        print(f'[eval] {name}: {path}')
        predict = spacy_predictor(path) if kind == 'spacy' else herbert_predictor(path)
        results[name] = evaluate(predict, gold_docs)

    if not results:
        print('No models found.')
        return

    names = list(results)
    print('\nOVERALL')
    print(f'{"model":<15} {"P":>7} {"R":>7} {"F":>7} {"tok/s":>9}')
    for n in names:
        r = results[n]
        print(f'{n:<15} {fmt(r["ents_p"]):>7} {fmt(r["ents_r"]):>7} {fmt(r["ents_f"]):>7} {r["tokens_per_sec"]:>9.0f}')

    labels = sorted({l for r in results.values() for l in (r.get('ents_per_type') or {})})
    print('\nF1 PER TYPE')
    print(f'{"label":<14}' + ''.join(f'{n:>15}' for n in names))
    for label in labels:
        row = [(results[n].get('ents_per_type') or {}).get(label, {}).get('f') for n in names]
        print(f'{label:<14}' + ''.join(f'{fmt(v):>15}' for v in row))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(results, fh, indent=2)
    print('\nSaved', args.out)


if __name__ == '__main__':
    main()
