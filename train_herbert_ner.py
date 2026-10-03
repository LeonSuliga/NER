"""Train a transformer NER model (HerBERT, Polish BERT) as a token classifier.

Reads the same spaCy DocBins as the spaCy models (data/spacy/*.spacy), so all three models
share one train/dev/test split. Each document is cut into windows of <= --max-length subwords;
the label of a word is predicted on its first subword. The checkpoint with the best dev
entity F1 is saved to --output (HF format) and can be loaded with HerbertTagger.

Usage:
  python train_herbert_ner.py --epochs 3
"""
import argparse
import math
import os
import random
import sys
import time

try:
    import spacy
    import torch
    from spacy.tokens import DocBin
    from transformers import AutoModelForTokenClassification, AutoTokenizer
except Exception as e:
    print('train_herbert_ner.py requires spacy, torch and transformers:', e)
    sys.exit(1)

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_SUBWORDS_PER_WORD = 16


def load_docs(path):
    """Return a list of (words, spaces, BIO tags) triples from a DocBin."""
    vocab = spacy.blank('pl').vocab
    out = []
    for doc in DocBin().from_disk(path).get_docs(vocab):
        words = [t.text for t in doc]
        spaces = [bool(t.whitespace_) for t in doc]
        tags = ['O' if t.ent_iob_ in ('O', '') else f'{t.ent_iob_}-{t.ent_type_}' for t in doc]
        out.append((words, spaces, tags))
    return out


def tags_to_spans(tags):
    """Convert BIO tags into (start, end, label) token spans; a stray I- starts a new span."""
    spans = []
    start, label = None, None
    for i, tag in enumerate(list(tags) + ['O']):
        if tag == 'O' or tag.startswith('B-') or (tag.startswith('I-') and tag[2:] != label):
            if label is not None:
                spans.append((start, i, label))
            start, label = (i, tag[2:]) if tag != 'O' else (None, None)
    return spans


class HerbertTagger:
    """Word-level tagger: split words into subword windows and predict one tag per word."""

    def __init__(self, model, tokenizer, max_length=256, device='cpu'):
        self.model = model
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.device = device
        self.id2label = {int(k): v for k, v in model.config.id2label.items()}
        self.label2id = {v: k for k, v in self.id2label.items()}

    @classmethod
    def load(cls, path, max_length=256, device=None):
        device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        tokenizer = AutoTokenizer.from_pretrained(path)
        model = AutoModelForTokenClassification.from_pretrained(path, dtype=torch.float32).to(device)
        model.eval()
        return cls(model, tokenizer, max_length, device)

    def word_pieces(self, words):
        enc = self.tokenizer(words, add_special_tokens=False)['input_ids']
        return [ids[:MAX_SUBWORDS_PER_WORD] or [self.tokenizer.unk_token_id] for ids in enc]

    def windows(self, words, tags=None):
        """Yield (input_ids, labels, first_subword_positions, word_offset) per window."""
        pieces = self.word_pieces(words)
        budget = self.max_length - 2
        i = 0
        while i < len(words):
            ids, labels, firsts = [self.tokenizer.cls_token_id], [-100], []
            j = i
            while j < len(words) and len(ids) - 1 + len(pieces[j]) <= budget:
                firsts.append(len(ids))
                ids.extend(pieces[j])
                lab = self.label2id[tags[j]] if tags is not None else 0
                labels.extend([lab] + [-100] * (len(pieces[j]) - 1))
                j += 1
            ids.append(self.tokenizer.sep_token_id)
            labels.append(-100)
            yield ids, labels, firsts, i
            i = j

    @torch.no_grad()
    def predict_tags(self, words, batch_size=16):
        tags = ['O'] * len(words)
        wins = list(self.windows(words))
        for b in range(0, len(wins), batch_size):
            batch = wins[b:b + batch_size]
            input_ids, attn = pad([w[0] for w in batch], self.tokenizer.pad_token_id)
            logits = self.model(input_ids=input_ids.to(self.device), attention_mask=attn.to(self.device)).logits
            pred = logits.argmax(-1).cpu().tolist()
            for (_, _, firsts, offset), row in zip(batch, pred):
                for k, pos in enumerate(firsts):
                    tags[offset + k] = self.id2label[row[pos]]
        return tags

    def predict_spans(self, words):
        return tags_to_spans(self.predict_tags(words))


def pad(seqs, pad_value):
    width = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), width), pad_value, dtype=torch.long)
    mask = torch.zeros((len(seqs), width), dtype=torch.long)
    for r, s in enumerate(seqs):
        ids[r, :len(s)] = torch.tensor(s)
        mask[r, :len(s)] = 1
    return ids, mask


def span_f1(tagger, docs):
    tp = n_pred = n_gold = 0
    for words, _, tags in docs:
        gold = set(tags_to_spans(tags))
        pred = set(tagger.predict_spans(words))
        tp += len(gold & pred)
        n_pred += len(pred)
        n_gold += len(gold)
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--train', default=os.path.join(ROOT, 'data', 'spacy', 'train.spacy'))
    ap.add_argument('--dev', default=os.path.join(ROOT, 'data', 'spacy', 'dev.spacy'))
    ap.add_argument('--output', default=os.path.join(ROOT, 'models', 'ner_herbert'))
    ap.add_argument('--base-model', default='allegro/herbert-base-cased')
    ap.add_argument('--epochs', type=int, default=3)
    ap.add_argument('--batch-size', type=int, default=8)
    ap.add_argument('--lr', type=float, default=5e-5)
    ap.add_argument('--max-length', type=int, default=256)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cpu':
        torch.set_num_threads(os.cpu_count() or 1)
    print('Device:', device)

    train_docs = load_docs(args.train)
    dev_docs = load_docs(args.dev)
    labels = sorted({t for _, _, tags in train_docs + dev_docs for t in tags} - {'O'})
    id2label = {0: 'O', **{i + 1: l for i, l in enumerate(labels)}}
    label2id = {l: i for i, l in id2label.items()}

    # Prefer the local cache: online loading of a .bin-only repo (like HerBERT) makes transformers
    # download a second, safetensors copy of the weights in the background.
    kwargs = dict(num_labels=len(id2label), id2label=id2label, label2id=label2id)
    try:
        tokenizer = AutoTokenizer.from_pretrained(args.base_model, local_files_only=True)
        model = AutoModelForTokenClassification.from_pretrained(args.base_model, local_files_only=True, **kwargs)
    except OSError:
        tokenizer = AutoTokenizer.from_pretrained(args.base_model)
        model = AutoModelForTokenClassification.from_pretrained(args.base_model, **kwargs)
    model.to(device)
    tagger = HerbertTagger(model, tokenizer, args.max_length, device)

    windows = [(ids, labs) for words, _, tags in train_docs for ids, labs, _, _ in tagger.windows(words, tags)]
    steps_per_epoch = math.ceil(len(windows) / args.batch_size)
    total_steps = steps_per_epoch * args.epochs
    warmup = max(1, int(0.1 * total_steps))
    print(f'Train windows: {len(windows)}, steps/epoch: {steps_per_epoch}, labels: {len(id2label)}')

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: min((s + 1) / warmup, max(0.0, (total_steps - s) / max(1, total_steps - warmup)))
    )

    best_f = -1.0
    for ep in range(args.epochs):
        model.train()
        random.shuffle(windows)
        t0, running = time.time(), 0.0
        for step in range(steps_per_epoch):
            batch = windows[step * args.batch_size:(step + 1) * args.batch_size]
            input_ids, attn = pad([b[0] for b in batch], tokenizer.pad_token_id)
            lab, _ = pad([b[1] for b in batch], -100)
            loss = model(input_ids=input_ids.to(device), attention_mask=attn.to(device), labels=lab.to(device)).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            running += loss.item()
            if (step + 1) % 20 == 0 or step + 1 == steps_per_epoch:
                print(f'Epoch {ep + 1}/{args.epochs} step {step + 1}/{steps_per_epoch} '
                      f'loss {running / (step + 1):.4f} ({time.time() - t0:.0f}s)', flush=True)

        model.eval()
        p, r, f = span_f1(tagger, dev_docs)
        print(f'Epoch {ep + 1} dev P={p:.4f} R={r:.4f} F={f:.4f}', flush=True)
        if f > best_f:
            best_f, best_epoch = f, ep + 1
            # Keep the best weights in memory as fp16 (halves the checkpoint; HerbertTagger.load casts back to fp32).
            best_state = {k: v.detach().half().cpu().clone() for k, v in model.state_dict().items()}

    # Write once at the end, removing the old weights first: overwriting in place needs twice the disk space.
    os.makedirs(args.output, exist_ok=True)
    old_weights = os.path.join(args.output, 'model.safetensors')
    if os.path.exists(old_weights):
        os.remove(old_weights)
    model.save_pretrained(args.output, state_dict=best_state)
    tokenizer.save_pretrained(args.output)
    print(f'Best dev F={best_f:.4f} (epoch {best_epoch}); saved to {args.output}')


if __name__ == '__main__':
    main()
