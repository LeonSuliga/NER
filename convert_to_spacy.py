import os, json, random, sys

IN = os.path.join(os.path.dirname(__file__), 'data', 'train_bio.json')
OUT_DIR = os.path.join(os.path.dirname(__file__), 'data')
TRAIN_OUT = os.path.join(OUT_DIR, 'train.spacy')
DEV_OUT = os.path.join(OUT_DIR, 'dev.spacy')
TEST_OUT = os.path.join(OUT_DIR, 'test.spacy')

# Load BIO training data and split it into spaCy train/dev/test bins.
with open(IN, 'r', encoding='utf-8') as fh:
    samples = json.load(fh)

random.seed(42)
random.shuffle(samples)
train_size = int(round(len(samples) * 0.8))
val_size = int(round(len(samples) * 0.1))
# ensure the remainder is kept for test and totals match all samples
train = samples[:train_size]
val = samples[train_size:train_size + val_size]
test = samples[train_size + val_size:]
if len(train) + len(val) + len(test) != len(samples):
    # keep the remainder for test if rounding produced a mismatch
    diff = len(samples) - (len(train) + len(val) + len(test))
    if diff != 0:
        test = samples[train_size + val_size:train_size + val_size + len(test) + diff]

try:
    import spacy
    from spacy.tokens import DocBin, Doc
    from spacy.vocab import Vocab
    from spacy.tokens import Span
except Exception as e:
    print('spaCy is required for convert_to_spacy.py. Please install spaCy (pip install spacy) and a Polish model or use spacy.blank("pl").')
    sys.exit(1)

nlp = spacy.blank('pl')
# helper to convert samples to Docs with token-level spans

def samples_to_docbin(examples):
    # Convert token-level BIO labels into spaCy Doc entities without overlapping spans.
    docbin = DocBin()
    for ex in examples:
        tokens = ex['tokens']
        tags = ex['tags']
        # build Doc from words (this keeps tokens as-is, avoids tokenization mismatches)
        doc = Doc(nlp.vocab, words=tokens)
        ents = []
        i = 0
        while i < len(tags):
            tag = tags[i]
            if tag == 'O':
                i += 1
                continue
            if tag.startswith('B-'):
                label = tag.split('-', 1)[1]
                start = i
                i += 1
                while i < len(tags) and tags[i].startswith('I-'):
                    i += 1
                end = i
                # create span
                try:
                    span = Span(doc, start, end, label=label)
                    ents.append(span)
                except Exception as e:
                    # skip misaligned
                    print('Warning: failed to create span', start, end, label, e)
            else:
                # I- without B-, skip
                i += 1
        # set ents (ensure no overlaps)
        # filter overlapping spans by keeping longest
        ents_sorted = sorted(ents, key=lambda s: (s.start, -s.end))
        filtered = []
        last_end = -1
        for s in ents_sorted:
            if s.start >= last_end:
                filtered.append(s)
                last_end = s.end
        doc.ents = filtered
        docbin.add(doc)
    return docbin

print('Converting', len(train), 'train,', len(val), 'val, and', len(test), 'test samples to spaCy DocBin...')
train_db = samples_to_docbin(train)
val_db = samples_to_docbin(val)
test_db = samples_to_docbin(test)

train_db.to_disk(TRAIN_OUT)
val_db.to_disk(DEV_OUT)
test_db.to_disk(TEST_OUT)
print('Wrote', TRAIN_OUT, 'and', DEV_OUT, 'and', TEST_OUT)
