"""
Loader script to populate PostgreSQL schema from staging JSONL files.

Features:
- Optionally executes schema.sql to create extensions/tables/indexes (--create-schema)
- Reads staging JSONL files (default ./staging/*.jsonl) and upserts into legal_acts and act_aliases
- Optional embedding generation via --embed-model (sentence-transformers). Embedding insertion requires the model to produce 1024-d vectors to match schema.sql (otherwise embeddings are skipped with a warning).

Usage examples:
  python load_pg.py --db-url postgresql://user:pass@localhost:5432/legaldb --create-schema
  python load_pg.py --db-url $DB_URL --staging-dir ./staging --embed-model all-mpnet-base-v2

Dependencies (requirements.txt): psycopg2-binary, pgvector, sentence-transformers (optional)
"""
import os
import glob
import json
import re
import argparse
import logging
from typing import List, Optional

# DB driver: prefer psycopg2, fallback to pg8000
try:
    import psycopg2
    from psycopg2.extras import execute_values
    _DB_DRIVER = 'psycopg2'
except Exception:
    psycopg2 = None
    execute_values = None
    try:
        import pg8000.dbapi as pg8000
        _DB_DRIVER = 'pg8000'
    except Exception:
        pg8000 = None
        _DB_DRIVER = None

# pgvector python lib optional; we'll avoid depending on it and insert vectors as SQL literals when needed
_HAS_PGVECTOR = False

try:
    from sentence_transformers import SentenceTransformer
    _HAS_SBM = True
except Exception:
    SentenceTransformer = None
    _HAS_SBM = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("load_pg")

DEFAULT_STAGING = os.path.join(os.path.dirname(__file__), "staging")

TITLE_CLEAN_RE = re.compile(r"[\(\)\[\]\:\,\;\"]|\b(\d{4})\b")


def clean_title(title: Optional[str]) -> str:
    if not title:
        return ""
    t = TITLE_CLEAN_RE.sub("", title)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def find_staging_files(staging_dir: str) -> List[str]:
    patterns = [os.path.join(staging_dir, "*.jsonl"), os.path.join(staging_dir, "*.ndjson")]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))
    return sorted(files)


def load_schema(conn, schema_path: str):
    logger.info("Applying schema from %s", schema_path)
    with open(schema_path, 'r', encoding='utf-8') as fh:
        sql = fh.read()
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    logger.info("Schema applied")


def process_file(conn, path: str, embed_model: Optional[SentenceTransformer], vector_dim: int = 1024):
    # Read staged acts and upsert them into the relational schema with deterministic fallback fields.
    logger.info("Processing staging file: %s", path)
    inserted = 0
    to_embed = []  # tuples (act_id, text)
    rows_upsert = []
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            act_id = item.get('id') or item.get('address')
            if not act_id:
                logger.warning("Skipping record without id/address: %s", item)
                continue
            publisher = item.get('publisher') or (item.get('address') or '').split('/')[0]
            year = item.get('year')
            position = item.get('position')
            # Infer year and position from act IDs when the API payload omits them.
            if (year is None or position is None) and act_id:
                m = re.match(r'^[A-Za-z]+(?P<y>\d{4})(?P<p>\d+)$', act_id)
                if m:
                    try:
                        if year is None:
                            year = int(m.group('y'))
                    except Exception:
                        year = None
                    try:
                        if position is None:
                            pos_str = m.group('p')
                            # strip leading zeros
                            pos = int(pos_str.lstrip('0') or '0')
                            position = pos
                    except Exception:
                        position = None
            title = item.get('title') or (item.get('raw') or {}).get('title') or ''
            title_clean = clean_title(title)
            act_type = item.get('type') or item.get('act_type')
            status = item.get('status')
            raw = item.get('raw') or item

            # ensure year and position are plain ints or NULL
            try:
                year = int(year) if year is not None else None
            except Exception:
                year = None
            try:
                position = int(position) if position is not None else None
            except Exception:
                position = None

            rows_upsert.append((act_id, publisher, year, position, title, title_clean, act_type, status, json.dumps(raw, ensure_ascii=False)))
            # candidate embedding text
            text_rep = title
            to_embed.append((act_id, text_rep))

    # Upsert legal_acts in batches to keep the loader idempotent across runs.
    cur = conn.cursor()
    sql = """
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
    """
    # executemany works for both psycopg2 and pg8000
    cur.executemany(sql, rows_upsert)
    conn.commit()
    inserted += len(rows_upsert)
    logger.info("Upserted %s legal_acts from %s", len(rows_upsert), path)

    # Insert alias rows for exact and fuzzy matching without duplicating existing entries.
    alias_rows = []
    for act_id, text in to_embed:
        if text:
            alias_rows.append((act_id, text, 'official_short'))
    if alias_rows:
        sql_alias = """
        INSERT INTO act_aliases (act_id, alias, alias_type)
        VALUES (%s, %s, %s)
        ON CONFLICT (act_id, alias, alias_type) DO NOTHING
        """
        cur.executemany(sql_alias, alias_rows)
    conn.commit()
    logger.info("Inserted/ignored %s alias rows", len(alias_rows))

    # embeddings
    if embed_model is None:
        logger.info("No embedding model provided: skipping embeddings for file %s", path)
        return inserted

    texts = [t for (_id, t) in to_embed]
    if not texts:
        logger.info("No texts to embed; skipping embedding step for file %s", path)
        return inserted
    logger.info("Computing embeddings for %d items (this may be slow)", len(texts))
    # try to get numpy array if possible; fallback to python lists
    try:
        embs = embed_model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    except TypeError:
        # fallback to non-numpy signature
        embs = embed_model.encode(texts)

    # verify dimension
    emb_dim = None
    try:
        emb_dim = embs.shape[1]
    except Exception:
        try:
            emb_dim = len(embs[0]) if embs and len(embs) > 0 else 0
        except Exception:
            emb_dim = 0
    if emb_dim != vector_dim:
        logger.warning("Embedding dimension %s does not match schema vector dim %s. Skipping embeddings.", emb_dim, vector_dim)
        return inserted

    # upsert embeddings
    rows = []
    # embs may be numpy array or python list
    if hasattr(embs, 'tolist'):
        embs_list = embs.tolist()
    else:
        embs_list = embs
    for (act_id, text), vec in zip(to_embed, embs_list):
        # format vector as Postgres vector literal string
        vec_str = '[' + ','.join(str(float(x)) for x in vec) + ']'
        rows.append((act_id, text, vec_str))
    sql_emb = """
    INSERT INTO act_embeddings (act_id, text_represented, embedding)
    VALUES (%s, %s, %s::vector)
    ON CONFLICT (act_id) DO UPDATE SET
        text_represented = EXCLUDED.text_represented,
        embedding = EXCLUDED.embedding,
        created_at = now()
    """
    cur.executemany(sql_emb, rows)
    conn.commit()
    logger.info("Upserted %d embeddings", len(rows))
    return inserted


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db-url', required=True, help='Postgres DSN, e.g. postgresql://user:pass@host:5432/db')
    p.add_argument('--staging-dir', default=DEFAULT_STAGING)
    p.add_argument('--schema', default=os.path.join(os.path.dirname(__file__), 'schema.sql'))
    p.add_argument('--create-schema', action='store_true')
    p.add_argument('--embed-model', help='Optional sentence-transformers model name or path')
    p.add_argument('--vector-dim', type=int, default=1024, help='Expected vector dimension (default 1024)')
    args = p.parse_args()

    staging_files = find_staging_files(args.staging_dir)
    if not staging_files:
        logger.error("No staging files found in %s", args.staging_dir)
        return

    # establish DB connection using available driver
    if _DB_DRIVER == 'psycopg2':
        conn = psycopg2.connect(args.db_url)
    elif _DB_DRIVER == 'pg8000':
        # parse DSN like postgresql://user:pass@host:port/db
        from urllib.parse import urlparse
        parsed = urlparse(args.db_url)
        user = parsed.username
        password = parsed.password
        host = parsed.hostname or 'localhost'
        port = parsed.port or 5432
        dbname = parsed.path.lstrip('/')
        conn = pg8000.connect(user=user, password=password, host=host, port=port, database=dbname)
    else:
        logger.error('No supported DB driver available (psycopg2 or pg8000 required)')
        return

    if args.create_schema:
        load_schema(conn, args.schema)

    embed_model = None
    # If sentence-transformers available and model requested, load it. Otherwise, provide deterministic fallback if requested.
    if args.embed_model:
        if _HAS_SBM:
            logger.info("Loading embed model: %s", args.embed_model)
            embed_model = SentenceTransformer(args.embed_model)
            logger.info("Model loaded")
        else:
            logger.warning("sentence-transformers not available; using deterministic fallback embedder for testing (not semantic).")
            # deterministic fallback embedder
            class FallbackEmbedder:
                def __init__(self, dim=768):
                    self.dim = dim
                def encode(self, texts, show_progress_bar=False, convert_to_numpy=False):
                    import hashlib, struct
                    import array
                    import math
                    outs = []
                    for t in texts:
                        if t is None:
                            t = ""
                        h = hashlib.sha256(t.encode('utf-8')).digest()
                        # expand digest to required dim by repeating
                        needed = self.dim
                        buf = bytearray()
                        while len(buf) < needed*4:
                            buf.extend(h)
                            h = hashlib.sha256(h).digest()
                        # interpret as floats in [-1,1]
                        arr = []
                        for i in range(needed):
                            # take 4 bytes
                            chunk = buf[i*4:(i+1)*4]
                            val = struct.unpack('>I', chunk)[0]  # 0..2^32-1
                            # map to -1..1
                            f = (val / 0xFFFFFFFF) * 2.0 - 1.0
                            arr.append(f)
                        # normalize vector
                        norm = math.sqrt(sum(x*x for x in arr)) or 1.0
                        arr = [x / norm for x in arr]
                        outs.append(arr)
                    if convert_to_numpy:
                        try:
                            import numpy as _np
                            return _np.array(outs, dtype='float32')
                        except Exception:
                            return outs
                    return outs
            embed_model = FallbackEmbedder(dim=args.vector_dim)
            logger.info("Fallback embedder initialized with dim=%s", args.vector_dim)

    total = 0
    for f in staging_files:
        total += process_file(conn, f, embed_model, vector_dim=args.vector_dim)

    logger.info("Done. Total processed rows: %s", total)
    conn.close()


if __name__ == '__main__':
    main()
