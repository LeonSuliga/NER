"""
Skeleton training script for NER fine-tuning.
Supports spaCy pipeline or Hugging Face Transformers training (skeleton only).

Usage:
  python train_ner.py --method spacy --data data/train_bio.json

This script does NOT run heavy training in this environment; it prepares data splits and evaluation flow.
"""
import argparse, json, random, os
try:
    from sklearn.model_selection import train_test_split
except Exception:
    # minimal fallback split
    def train_test_split(data, test_size=0.2, random_state=None):
        if random_state is not None:
            import random as _r
            _r.seed(random_state)
            _r.shuffle(data)
        n = int(len(data) * (1-test_size))
        return data[:n], data[n:]

def load_bio_json(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def to_spacy_format(samples):
    # convert our tokens/tags to spaCy training tuples (text, {'entities': [(start, end, label), ...]})
    out = []
    for s in samples:
        tokens = s['tokens']
        tags = s['tags']
        text = ' '.join(tokens)
        entities = []
        char = 0
        for tok, tag in zip(tokens, tags):
            start = char
            end = char + len(tok)
            if tag != 'O':
                if tag.startswith('B-'):
                    label = tag.split('-',1)[1]
                    # find full span (collect subsequent I- tags)
                    j = tokens.index(tok)
                    # naive: expand forward
                    span_end = end
                    k = 1
                    while j + k < len(tags) and tags[j+k].startswith('I-'):
                        span_end += 1 + len(tokens[j+k])
                        k += 1
                    entities.append((start, span_end, label))
            char = end + 1
        out.append((text, {'entities': entities}))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default=os.path.join('data','train_bio.json'))
    args = p.parse_args()

    samples = load_bio_json(args.data)
    train, val = train_test_split(samples, test_size=0.2, random_state=42)
    print('Samples:', len(samples), 'Train:', len(train), 'Val:', len(val))
    print('\nFirst 5 training examples (tokens/tags):')
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    for ex in train[:5]:
        print(ex['tokens'])
        print(ex['tags'])
        print('---')

if __name__ == '__main__':
    main()
