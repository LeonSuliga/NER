import os, json, glob, random, re
from typing import List

random.seed(42)
STAGING_DIR = os.path.join(os.path.dirname(__file__), 'staging')
OUT_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(OUT_DIR, exist_ok=True)

# collect sample acts from staging
files = sorted(glob.glob(os.path.join(STAGING_DIR, '*.jsonl')))
acts = []
for p in files:
    with open(p, 'r', encoding='utf-8') as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except Exception:
                continue
            act_id = item.get('id') or item.get('address')
            title = item.get('title') or (item.get('raw') or {}).get('title') or ''
            publisher = item.get('publisher') or ''
            year = item.get('year')
            position = item.get('position')
            act_type = item.get('type') or item.get('act_type') or ''
            if act_id and title:
                acts.append({'id': act_id, 'title': title, 'publisher': publisher, 'year': year, 'position': position, 'type': act_type})

if not acts:
    # fallback minimal set
    acts = [
        {'id': 'WDU20200000001', 'title': 'Kodeks cywilny', 'publisher': 'DU', 'year': 2020, 'position': 1, 'type': 'ustawa'},
        {'id': 'WDU20200000002', 'title': 'Prawo o ruchu drogowym', 'publisher': 'DU', 'year': 2020, 'position': 2, 'type': 'rozporządzenie'},
    ]

# Build legal-sounding sentence templates that mimic citations in Polish acts.
templates = [
    "Na podstawie {pinpoint} {law_type} z dnia {date} - {law_title} ({publisher_text} z {year} r. poz. {position}) orzeka się, że...",
    "Zgodnie z {pinpoint} {law_type} {law_title} ({publisher_text} {year} poz. {position}) przepisy stosuje się w zakresie...",
    "W myśl {pinpoint} ustawy {law_title} ({publisher_text} z {year} r., poz. {position}) sąd uwzględnił...",
    "Powołując się na {pinpoint} {law_title} ({publisher_text} {year} poz. {position}), stwierdza się, że...",
    "Na podstawie art. {art} ust. {ust} {law_title} ({publisher_text} {year} poz. {position}) wydano decyzję...",
    "Zgodnie z przepisami {law_title} (Dz. U. {year} poz. {position}) oraz {pinpoint} orzeka się co następuje...",
]

publisher_map = {
    'DU': 'Dz. U.',
    'MP': 'M.P.',
}

pinpoint_samples = [
    'art. 5', 'art. 5 ust. 2', 'art. 12', 'art. 3 pkt 4', 'par. 7', '§ 4', 'art. 10a', 'art. 15 ust. 1 i 2'
]

sentences = []
num = 250
# Generate 250 synthetic sentences with span annotations for each target entity type.
for i in range(num):
    a = random.choice(acts)
    law_title = a['title']
    law_type = a['type'] or random.choice(['ustawa', 'rozporządzenie', 'uchwała'])
    publisher_code = a.get('publisher') or random.choice(['DU','MP'])
    publisher_text = publisher_map.get(publisher_code, publisher_code)
    year = a.get('year') or random.randint(1990, 2023)
    position = a.get('position') or random.randint(1, 3000)
    date = f"{random.randint(1,28)} {random.choice(['stycznia','lutego','marca','kwietnia','maja','czerwca','lipca','sierpnia','września','października','listopada','grudnia'])} {year} r."
    template = random.choice(templates)
    art = random.randint(1,40)
    ust = random.randint(1,5)
    pinpoint = random.choice(pinpoint_samples)
    text = template.format(pinpoint=pinpoint, law_type=law_type, date=date, law_title=law_title, publisher_text=publisher_text, year=year, position=position, art=art, ust=ust)
    # build spans with character offsets for nested JSON format
    spans = []
    # LAW_TITLE: find law_title occurrence
    idx = text.find(law_title)
    if idx != -1:
        spans.append({'label': 'LAW_TITLE', 'start': idx, 'end': idx+len(law_title)})
    # PUBLISHER: find publisher_text
    idx = text.find(publisher_text)
    if idx != -1:
        spans.append({'label': 'PUBLISHER', 'start': idx, 'end': idx+len(publisher_text)})
    # PUB_YEAR: find the year occurrence (as string)
    ystr = str(year)
    idx = text.find(ystr)
    if idx != -1:
        spans.append({'label': 'PUB_YEAR', 'start': idx, 'end': idx+len(ystr)})
    # PUB_POS: find 'poz. {position}'
    pstr = f"poz. {position}"
    idx = text.find(pstr)
    if idx != -1:
        spans.append({'label': 'PUB_POS', 'start': idx, 'end': idx+len(pstr)})
    # PINPOINT: find pinpoint
    idx = text.find(pinpoint)
    if idx != -1:
        spans.append({'label': 'PINPOINT', 'start': idx, 'end': idx+len(pinpoint)})
    sample = {'text': text, 'spans': spans, 'meta': {'source_act_id': a['id'], 'publisher_code': publisher_code}}
    sentences.append(sample)

out_path = os.path.join(OUT_DIR, 'ner_dataset.json')
with open(out_path, 'w', encoding='utf-8') as fh:
    json.dump(sentences, fh, ensure_ascii=False, indent=2)

print('Generated', len(sentences), 'samples ->', out_path)
