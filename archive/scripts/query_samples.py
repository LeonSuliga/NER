import sys
import pg8000.dbapi as pg

# ensure UTF-8 output on Windows console
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

conn = pg.connect(user='postgres', password='postgres', host='localhost', port=5432, database='legaldb')
cur = conn.cursor()
cur.execute("SELECT id, publisher, year, position, title, act_type, status FROM legal_acts WHERE publisher='DU' LIMIT 3")
rows = cur.fetchall()
print('LEGAL_ACTS:')
for r in rows:
    id_, publisher, year, position, title, act_type, status = r
    print(f"id={id_} publisher={publisher} year={year} position={position}")
    print("  title=", title)
    act_id = id_
    cur2 = conn.cursor()
    cur2.execute('SELECT alias, alias_type FROM act_aliases WHERE act_id=%s LIMIT 5', (act_id,))
    aliases = cur2.fetchall()
    print('  ALIASES:', aliases)

cur.execute("SELECT act_id, text_represented FROM act_embeddings WHERE act_id IN (SELECT id FROM legal_acts WHERE publisher='DU' LIMIT 3)")
print('\nEMBEDDINGS:')
for r in cur.fetchall():
    print(r[0], (r[1] or '')[:80])

cur.close()
conn.close()
