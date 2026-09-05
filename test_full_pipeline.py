import time, sys, os
# ensure project root and UTF-8 output
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from regex_ner import parse as regex_parse
from entity_linker import LegalEntityLinker

DB = 'postgresql://postgres:postgres@localhost:5432/legaldb'

# Run a few representative legal references through the rule parser and linker.
examples = [
    "Na podstawie art. 5 ust. 2 ustawy z dnia 23 kwietnia 1964 r. - Kodeks cywilny (Dz. U. z 2020 r. poz. 1) orzeka się, że...",
    "Zgodnie z Rozporządzeniem Ministra Finansów z dnia 23 grudnia 2019 r. (Dz. U. 2020 poz. 2) stosuje się środki...",
    "Powołując się na art. 12 Rozporządzenie Ministra Finansów z dnia 31 grudnia 2019 r. w sprawie postępowania kwalifikacyjnego (Dz. U. z 2020 r. poz. 2) wydano postanowienie..."
]

linker = LegalEntityLinker(DB, embed_model_name='fallback', vector_dim=768)

for txt in examples:
    start = time.time()
    parsed = regex_parse(txt)
    result = linker.resolve_citation(parsed)
    took = time.time() - start
    print('TEXT:')
    print(txt)
    print('PARSED:')
    print(parsed)
    print('RESULT:')
    print(result)
    print('TIME:', f'{took:.3f}s')
    print('---')

linker.close()
