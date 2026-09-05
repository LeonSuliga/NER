import os, sys

try:
    import spacy
    from spacy.tokens import DocBin
except Exception:
    print('spaCy not installed; train_spacy_ner.py requires spaCy. Install it in your venv (pip install spacy) and a Polish model or use spacy.blank("pl").')
    sys.exit(1)

import argparse

p = argparse.ArgumentParser()
p.add_argument('--train', default=os.path.join('data','train.spacy'))
p.add_argument('--dev', default=os.path.join('data','dev.spacy'))
p.add_argument('--output', default=os.path.join('models','ner_spacy'))
p.add_argument('--epochs', type=int, default=10)
args = p.parse_args()

# Load the binary spaCy training set and initialize a blank Polish NER model.
train_db = DocBin().from_disk(args.train)
dev_db = DocBin().from_disk(args.dev)
train_docs = list(train_db.get_docs(spacy.blank('pl').vocab))

# prepare nlp
nlp = spacy.blank('pl')
if 'ner' not in nlp.pipe_names:
    ner = nlp.add_pipe('ner')
else:
    ner = nlp.get_pipe('ner')

# collect labels
labels = set()
for d in train_docs:
    for ent in d.ents:
        labels.add(ent.label_)
for l in labels:
    ner.add_label(l)

# disable other pipes
other_pipes = [p for p in nlp.pipe_names if p != 'ner']

with nlp.select_pipes(disable=other_pipes):
    optimizer = nlp.initialize(lambda: train_docs)
    for ep in range(args.epochs):
        losses = {}
        # naïve training: iterate docs
        random_order = train_docs[:]
        import random
        random.shuffle(random_order)
        for doc in random_order:
            example = (doc.text, {'entities': [(ent.start_char, ent.end_char, ent.label_) for ent in doc.ents]})
            nlp.update([example[0]], [example[1]], sgd=optimizer, drop=0.2, losses=losses)
        print(f'Epoch {ep+1}/{args.epochs} losses:', losses)

# save model
os.makedirs(args.output, exist_ok=True)
nlp.to_disk(args.output)
print('Saved model to', args.output)
