import pg8000.dbapi as pg
conn = pg.connect(user='postgres', password='postgres', host='localhost', port=5432, database='legaldb')
cur = conn.cursor()
cur.execute("SELECT count(*) FROM legal_acts WHERE year IS NULL OR position IS NULL")
print('rows_with_null_year_or_position =', cur.fetchone()[0])
cur.execute("SELECT id, year, position FROM legal_acts ORDER BY id LIMIT 10")
for r in cur.fetchall():
    print(r)
cur.close(); conn.close()
