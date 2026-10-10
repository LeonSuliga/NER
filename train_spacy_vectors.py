"""Train a second spaCy NER model: tok2vec + NER with pretrained Polish word vectors.

Differs from train_spacy_ner.py (blank model, hand-written loop) by using the official
`spacy train` loop with configs/ner_spacy_vectors.cfg, static vectors from pl_core_news_md,
and model selection on the dev set (model-best).

Requires: python -m spacy download pl_core_news_md
"""
import argparse
import os
import sys

try:
    from spacy.cli.train import train
except Exception:
    print('spaCy not installed; train_spacy_vectors.py requires spaCy (pip install spacy).')
    sys.exit(1)

ROOT = os.path.dirname(os.path.abspath(__file__))

p = argparse.ArgumentParser()
p.add_argument('--config', default=os.path.join(ROOT, 'configs', 'ner_spacy_vectors.cfg'))
p.add_argument('--train', default=os.path.join(ROOT, 'data', 'spacy', 'train.spacy'))
p.add_argument('--dev', default=os.path.join(ROOT, 'data', 'spacy', 'dev.spacy'))
p.add_argument('--output', default=os.path.join(ROOT, 'models', 'ner_spacy_vectors'))
p.add_argument('--vectors', default='pl_core_news_md', help='spaCy package or path with word vectors')
p.add_argument('--max-steps', type=int, default=None)
p.add_argument('--chunk-tokens', type=int, default=200,
               help='split training docs into ~N-token chunks (0 = keep whole docs)')
args = p.parse_args()


def chunk_doc(doc, size):
    """Split a doc after a '.' once a chunk reaches `size` tokens (hard cut at 2*size), never inside an entity."""
    chunks, start = [], 0
    for i, tok in enumerate(doc):
        end = i + 1
        if end >= len(doc):
            break
        length = end - start
        inside_ent = doc[end].ent_iob_ == 'I'
        if not inside_ent and ((length >= size and tok.text == '.') or length >= 2 * size):
            chunks.append(doc[start:end].as_doc())
            start = end
    chunks.append(doc[start:].as_doc())
    return chunks


# Long legal acts (up to ~40k tokens) make each `spacy train` step very slow, so train on chunks.
train_path = args.train
if args.chunk_tokens > 0:
    import spacy
    from spacy.tokens import DocBin
    vocab = spacy.blank('pl').vocab
    chunked = DocBin()
    n_docs = 0
    for doc in DocBin().from_disk(args.train).get_docs(vocab):
        n_docs += 1
        for c in chunk_doc(doc, args.chunk_tokens):
            chunked.add(c)
    train_path = os.path.join(os.path.dirname(args.train), 'train_chunks.spacy')
    chunked.to_disk(train_path)
    print(f'Split {n_docs} training docs into {len(chunked)} chunks -> {train_path}')

overrides = {
    'paths.train': train_path,
    'paths.dev': args.dev,
    'paths.vectors': args.vectors,
}
if args.max_steps is not None:
    overrides['training.max_steps'] = args.max_steps

os.makedirs(args.output, exist_ok=True)
train(args.config, args.output, overrides=overrides)
print('Saved model to', os.path.join(args.output, 'model-best'))
