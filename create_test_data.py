"""
Create test records in Postgres to validate entity_linker.
Inserts one legal_act, aliases, and an embedding computed by deterministic fallback.
"""
import pg8000.dbapi as pg
import hashlib, struct, math

DB_DSN = {
    'user': 'postgres',
    'password': 'postgres',
    'host': 'localhost',
    'port': 5432,
    'database': 'legaldb'
}

ACT_ID = 'WDU19640160093'
PUBLISHER = 'dziennik_ustaw'
YEAR = 1964
POSITION = 1600
TITLE = 'Kodeks cywilny'
ACT_TYPE = 'ustawa'
STATUS = 'obowiązujący'
VECTOR_DIM = 768

# deterministic fallback embedder
def fallback_encode(text, dim=VECTOR_DIM):
    if text is None:
        text = ''
    h = hashlib.sha256(text.encode('utf-8')).digest()
    buf = bytearray()
    while len(buf) < dim*4:
        buf.extend(h)
        h = hashlib.sha256(h).digest()
    arr = []
    for i in range(dim):
        chunk = buf[i*4:(i+1)*4]
        val = struct.unpack('>I', chunk)[0]
        f = (val / 0xFFFFFFFF) * 2.0 - 1.0
        arr.append(f)
    norm = math.sqrt(sum(x*x for x in arr)) or 1.0
    arr = [x / norm for x in arr]
    return arr

vec = fallback_encode(TITLE)
vec_str = '[' + ','.join(str(float(x)) for x in vec) + ']'

conn = pg.connect(**DB_DSN)
cur = conn.cursor()

# upsert legal_acts
cur.execute("""
INSERT INTO legal_acts (id, publisher, year, position, title, title_clean, act_type, status, raw)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
  publisher = EXCLUDED.publisher,
  year = EXCLUDED.year,
  position = EXCLUDED.position,
  title = EXCLUDED.title,
  title_clean = EXCLUDED.title_clean,
  act_type = EXCLUDED.act_type,
  status = EXCLUDED.status,
  raw = EXCLUDED.raw
""", (ACT_ID, PUBLISHER, YEAR, POSITION, TITLE, TITLE, ACT_TYPE, STATUS, '{}'))

# insert aliases
cur.execute("""
INSERT INTO act_aliases (act_id, alias, alias_type)
VALUES (%s, %s, %s)
ON CONFLICT (act_id, alias, alias_type) DO NOTHING
""", (ACT_ID, TITLE, 'official_short'))
cur.execute("""
INSERT INTO act_aliases (act_id, alias, alias_type)
VALUES (%s, %s, %s)
ON CONFLICT (act_id, alias, alias_type) DO NOTHING
""", (ACT_ID, 'kc', 'abbrev'))

# upsert embedding
cur.execute("""
INSERT INTO act_embeddings (act_id, text_represented, embedding)
VALUES (%s, %s, %s::vector)
ON CONFLICT (act_id) DO UPDATE SET
  text_represented = EXCLUDED.text_represented,
  embedding = EXCLUDED.embedding,
  created_at = now()
""", (ACT_ID, TITLE, vec_str))

conn.commit()
cur.close()
conn.close()
print('Inserted test act', ACT_ID)
