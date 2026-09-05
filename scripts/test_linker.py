import sys, os
# ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# ensure UTF-8 output
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from entity_linker import LegalEntityLinker

DB='postgresql://postgres:postgres@localhost:5432/legaldb'
linker = LegalEntityLinker(DB, embed_model_name='fallback', vector_dim=768)

tests = [
    {'publisher':'DU','year':2020,'position':1, 'citation_text': None},
    {'citation_text':'Rozporządzenie Ministra Finansów z dnia 31 grudnia 2019 r. w sprawie postępowania kwalifikacyjnego'}
]
for t in tests:
    res = linker.resolve_citation(t)
    print('Input:', t)
    print('Result:', res)
    print('---')

linker.close()
