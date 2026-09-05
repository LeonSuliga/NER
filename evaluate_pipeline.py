import os, sys, json, random
from collections import defaultdict

# ensure project imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from regex_ner import parse as regex_parse
from entity_linker import LegalEntityLinker

DATA = os.path.join(os.path.dirname(__file__), 'data', 'train_bio.json')

with open(DATA, 'r', encoding='utf-8') as fh:
    samples = json.load(fh)

# Split the synthetic dataset into train and validation buckets for evaluation.
random.seed(42)
random.shuffle(samples)
split = int(len(samples)*0.8)
train = samples[:split]
dev = samples[split:]

# Convert BIO labels into a normalized structure comparable with regex output.
def gold_normalized_from_sample(s):
    tokens = s['tokens']
    tags = s['tags']
    out = {'publisher': None, 'pub_year': None, 'position': None, 'pinpoint': None, 'law_title': None}
    i = 0
    while i < len(tags):
        if tags[i] == 'O':
            i += 1
            continue
        if tags[i].startswith('B-'):
            lab = tags[i].split('-',1)[1]
            start = i
            i += 1
            while i < len(tags) and tags[i].startswith('I-'):
                i += 1
            end = i
            text = ' '.join(tokens[start:end])
            if lab == 'PUBLISHER':
                # normalize publisher tokens to code
                if 'Dz' in text or 'Dziennik' in text:
                    out['publisher'] = 'DU'
                elif 'M.P' in text or 'Monitor' in text:
                    out['publisher'] = 'MP'
                else:
                    out['publisher'] = text
            elif lab == 'PUB_YEAR':
                digits = ''.join(ch for ch in text if ch.isdigit())
                try:
                    out['pub_year'] = int(digits)
                except Exception:
                    out['pub_year'] = None
            elif lab == 'PUB_POS':
                digits = ''.join(ch for ch in text if ch.isdigit())
                try:
                    out['position'] = int(digits)
                except Exception:
                    out['position'] = None
            elif lab == 'PINPOINT':
                out['pinpoint'] = text
            elif lab == 'LAW_TITLE':
                out['law_title'] = text
        else:
            i += 1
    return out

# prepare linker
DB='postgresql://postgres:postgres@localhost:5432/legaldb'
# Prepare the linker for end-to-end evaluation after field-level comparison.
linker = LegalEntityLinker(DB, embed_model_name='fallback', vector_dim=768)

# run regex baseline on dev
label_stats = defaultdict(lambda: {'tp':0,'fp':0,'fn':0})
end2end_counts = {'regex_correct':0,'regex_total':0,'model_correct':0,'model_total':0}

# try to load spaCy model if exists
spacy_model_path = os.path.join('models','ner_spacy')
use_model = False
try:
    import spacy
    if os.path.isdir(spacy_model_path):
        nlp_model = spacy.load(spacy_model_path)
        use_model = True
    else:
        nlp_model = None
except Exception:
    nlp_model = None
    use_model = False

# Run the regex baseline and optional spaCy model against each dev sample.
import time
regex_times = []
model_times = []
for s in dev:
    text = ' '.join(s['tokens'])
    gold = gold_normalized_from_sample(s)
    # Regex parse
    t0 = time.time()
    parsed = regex_parse(text)
    t1 = time.time()
    regex_times.append(t1-t0)
    # normalize regex parsed to comparable fields
    pred = {'publisher': parsed.get('publisher'), 'pub_year': parsed.get('pub_year'), 'position': parsed.get('position'), 'pinpoint': parsed.get('pinpoint'), 'law_title': parsed.get('law_title')}
    # update per-field stats
    for field in ['publisher','pub_year','position','pinpoint','law_title']:
        g = gold.get(field)
        p = pred.get(field)
        if g is None and p is None:
            continue
        if g == p:
            label_stats[field]['tp'] += 1
        else:
            if p is not None:
                label_stats[field]['fp'] += 1
            if g is not None:
                label_stats[field]['fn'] += 1
    # end-to-end for regex
    res = linker.resolve_citation(parsed)
    end2end_counts['regex_total'] += 1
    if res.get('id') == s.get('meta',{}).get('source_act_id'):
        end2end_counts['regex_correct'] += 1

    # model baseline if available
    if use_model:
        t0 = time.time()
        doc = nlp_model(text)
        t1 = time.time()
        model_times.append(t1-t0)
        # build pred dict from model ents
        mp = {'publisher': None, 'pub_year': None, 'position': None, 'pinpoint': None, 'law_title': None}
        for ent in doc.ents:
            lab = ent.label_
            txt = ent.text
            if lab == 'PUBLISHER':
                if 'Dz' in txt or 'Dziennik' in txt:
                    mp['publisher'] = 'DU'
                elif 'M.P' in txt or 'Monitor' in txt:
                    mp['publisher'] = 'MP'
                else:
                    mp['publisher'] = txt
            elif lab == 'PUB_YEAR':
                digits = ''.join(ch for ch in txt if ch.isdigit())
                try:
                    mp['pub_year'] = int(digits)
                except Exception:
                    mp['pub_year'] = None
            elif lab == 'PUB_POS':
                digits = ''.join(ch for ch in txt if ch.isdigit())
                try:
                    mp['position'] = int(digits)
                except Exception:
                    mp['position'] = None
            elif lab == 'PINPOINT':
                mp['pinpoint'] = txt
            elif lab == 'LAW_TITLE':
                mp['law_title'] = txt
        # update per-field stats for model
        for field in ['publisher','pub_year','position','pinpoint','law_title']:
            g = gold.get(field)
            p = mp.get(field)
            if g is None and p is None:
                continue
            if g == p:
                label_stats[field]['tp'] += 1
            else:
                if p is not None:
                    label_stats[field]['fp'] += 1
                if g is not None:
                    label_stats[field]['fn'] += 1
        # end-to-end via linker
        model_parsed = {}
        if mp['publisher']:
            model_parsed['publisher'] = mp['publisher']
        if mp['pub_year']:
            model_parsed['year'] = mp['pub_year']
        if mp['position']:
            model_parsed['position'] = mp['position']
        if mp['pinpoint']:
            model_parsed['citation_text'] = mp['pinpoint']
        resm = linker.resolve_citation(model_parsed)
        end2end_counts['model_total'] += 1
        if resm.get('id') == s.get('meta',{}).get('source_act_id'):
            end2end_counts['model_correct'] += 1

# compute metrics
print('\nField-level metrics:')
print('FIELD\tTP\tFP\tFN\tPREC\tREC\tF1\tTIME(ms)')
for field,st in label_stats.items():
    tp = st['tp']; fp = st['fp']; fn = st['fn']
    prec = tp / (tp+fp) if tp+fp>0 else 0.0
    rec = tp / (tp+fn) if tp+fn>0 else 0.0
    f1 = 2*prec*rec/(prec+rec) if prec+rec>0 else 0.0
    # avg time per sample (regex or model)
    time_ms = None
    if field in ['publisher','pub_year','position','pinpoint','law_title']:
        time_ms = (sum(regex_times)/len(regex_times))*1000 if regex_times else 0
    print(f"{field}\t{tp}\t{fp}\t{fn}\t{prec:.3f}\t{rec:.3f}\t{f1:.3f}\t{time_ms:.1f}")

print('\nEnd-to-End accuracy:')
print('Regex: {}/{} = {:.3f}'.format(end2end_counts['regex_correct'], end2end_counts['regex_total'], end2end_counts['regex_correct']/end2end_counts['regex_total'] if end2end_counts['regex_total'] else 0))
if use_model:
    print('Model: {}/{} = {:.3f}'.format(end2end_counts['model_correct'], end2end_counts['model_total'], end2end_counts['model_correct']/end2end_counts['model_total'] if end2end_counts['model_total'] else 0))
    print('\nAvg processing time per sample (ms): Regex={:.2f} ms, Model={:.2f} ms'.format((sum(regex_times)/len(regex_times))*1000,(sum(model_times)/len(model_times))*1000 if model_times else 0))
else:
    print('Model: not evaluated (no trained spaCy model found)')

linker.close()
