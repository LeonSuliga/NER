"""
Entity linking module for legal citations.

Class: LegalEntityLinker
Methods:
  - resolve_citation(parsed_ner_dict) -> dict

Resolution steps (in order):
  1) Exact Match on publisher/year/position -> confidence 1.0
  2) Fuzzy/Alias Match using act_aliases and trigram similarity -> confidence based on similarity
  3) Vector Match using act_embeddings and pgvector -> confidence based on cosine similarity threshold (>=0.82)

The module uses psycopg2 for DB access and optional sentence-transformers for embeddings. It handles missing optional deps gracefully.
"""
from typing import Optional, Dict, Any, List, Tuple
import logging
import math

# Database driver fallback: prefer psycopg2, fallback to pg8000 (pure-python)
try:
    import psycopg2
    _DB_DRIVER = 'psycopg2'
    _HAS_PG = True
except Exception:
    psycopg2 = None
    try:
        import pg8000.dbapi as pg8000
        _DB_DRIVER = 'pg8000'
        _HAS_PG = True
    except Exception:
        pg8000 = None
        _DB_DRIVER = None
        _HAS_PG = False

try:
    from sentence_transformers import SentenceTransformer
    _HAS_SB = True
except Exception:
    SentenceTransformer = None
    _HAS_SB = False

logger = logging.getLogger("entity_linker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class LegalEntityLinker:
    def __init__(self, db_dsn: str, embed_model_name: Optional[str] = None, vector_dim: int = 1024):
        # Create the Postgres connection and optional deterministic fallback embedder for vector lookup.
        if not _HAS_PG:
            raise RuntimeError("No supported Postgres driver installed. Install psycopg2-binary or pg8000.")
        self.db_dsn = db_dsn
        self.vector_dim = vector_dim
        self.embed_model = None
        # establish connection based on available driver
        if _DB_DRIVER == 'psycopg2':
            # psycopg2 accepts DSN string
            self.conn = psycopg2.connect(db_dsn)
        elif _DB_DRIVER == 'pg8000':
            # parse DSN like postgresql://user:pass@host:port/db
            from urllib.parse import urlparse
            parsed = urlparse(db_dsn)
            user = parsed.username
            password = parsed.password
            host = parsed.hostname or 'localhost'
            port = parsed.port or 5432
            dbname = parsed.path.lstrip('/')
            self.conn = pg8000.connect(user=user, password=password, host=host, port=port, database=dbname)
        else:
            raise RuntimeError('Unsupported DB driver')

        if embed_model_name:
            if _HAS_SB:
                logger.info("Loading embedding model: %s", embed_model_name)
                self.embed_model = SentenceTransformer(embed_model_name)
            else:
                # provide deterministic fallback if requested
                if embed_model_name == 'fallback':
                    logger.warning("Using deterministic fallback embedder for vector matching (not semantic).")
                    import hashlib, struct, math
                    class FallbackEmbed:
                        def __init__(self, dim):
                            self.dim = dim
                        def encode(self, texts, convert_to_numpy=False):
                            outs = []
                            for t in texts:
                                if t is None:
                                    t = ''
                                h = hashlib.sha256(t.encode('utf-8')).digest()
                                buf = bytearray()
                                while len(buf) < self.dim*4:
                                    buf.extend(h)
                                    h = hashlib.sha256(h).digest()
                                arr = []
                                for i in range(self.dim):
                                    chunk = buf[i*4:(i+1)*4]
                                    val = struct.unpack('>I', chunk)[0]
                                    f = (val / 0xFFFFFFFF) * 2.0 - 1.0
                                    arr.append(f)
                                norm = math.sqrt(sum(x*x for x in arr)) or 1.0
                                arr = [x / norm for x in arr]
                                outs.append(arr)
                            if convert_to_numpy:
                                try:
                                    import numpy as _np
                                    return _np.array(outs, dtype='float32')
                                except Exception:
                                    # numpy not available, return python list
                                    return outs
                            return outs
                    self.embed_model = FallbackEmbed(vector_dim)
                else:
                    logger.warning("sentence-transformers not installed; vector matching will be disabled")

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # Step 1: Exact match
    def _exact_match(self, publisher: Optional[str], year: Optional[int], position: Optional[int]) -> Optional[Dict[str, Any]]:
        # Query exact legal_act rows by publisher, publication year, and position.
        if not (publisher and year and position):
            return None
        sql = """
        SELECT id FROM legal_acts WHERE publisher = %s AND year = %s AND position = %s LIMIT 1
        """
        cur = self.conn.cursor()
        cur.execute(sql, (publisher, year, position))
        rows = cur.fetchall()
        # convert to dict using cursor.description
        if rows:
            cols = [c[0] for c in cur.description]
            row0 = dict(zip(cols, rows[0]))
            return {"id": row0.get('id'), "confidence": 1.0, "method": "exact"}
        return None

    # Step 2: Fuzzy / alias match
    def _fuzzy_alias_match(self, text: str, top_n: int = 5) -> Optional[Dict[str, Any]]:
        # Fall back to alias and trigram matching when exact citation metadata is incomplete.
        if not text or text.strip() == "":
            return None
        # First search act_aliases using trigram similarity if pg_trgm available via % operator
        results: List[Tuple[str, float, str]] = []  # (act_id, sim, source)
        cur = self.conn.cursor()
        try:
            cur.execute("""
                SELECT act_id, alias, similarity(alias, %s) AS sim
                FROM act_aliases
                WHERE alias %% %s
                ORDER BY sim DESC
                LIMIT %s
            """, (text, text, top_n))
            rows = cur.fetchall()
            if rows:
                cols = [c[0] for c in cur.description]
                for r in rows:
                    rowd = dict(zip(cols, r))
                    results.append((rowd['act_id'], float(rowd.get('sim') or 0.0), 'alias'))
        except Exception as e:
            logger.debug("Alias similarity query failed: %s", e)
        try:
            cur.execute("""
                SELECT id, title, similarity(title, %s) AS sim
                FROM legal_acts
                WHERE title %% %s
                ORDER BY sim DESC
                LIMIT %s
            """, (text, text, top_n))
            rows = cur.fetchall()
            if rows:
                cols = [c[0] for c in cur.description]
                for r in rows:
                    rowd = dict(zip(cols, r))
                    results.append((rowd['id'], float(rowd.get('sim') or 0.0), 'title'))
        except Exception as e:
            logger.debug("Title similarity query failed: %s", e)
        if not results:
            return None
        # pick best
        results.sort(key=lambda x: x[1], reverse=True)
        best_act, best_sim, source = results[0]
        # Map similarity to confidence (simple linear mapping, cap at 0.95)
        # pg_trgm similarity ranges 0..1 roughly; choose threshold 0.4
        if best_sim < 0.35:
            return None
        confidence = min(0.95, 0.5 + (best_sim - 0.35))
        return {"id": best_act, "confidence": round(confidence, 3), "method": f"fuzzy_{source}", "score": best_sim}

    # Step 3: Vector match
    def _vector_match(self, text: str, threshold: float = 0.82, top_k: int = 5) -> Optional[Dict[str, Any]]:
        # Use semantic ranking only when an embedding model and vector index are available.
        if not text or text.strip() == "":
            return None
        if not self.embed_model:
            logger.debug("No embed model loaded; skipping vector match")
            return None
        emb = self.embed_model.encode([text], convert_to_numpy=True)
        if emb is None:
            return None
        # emb can be numpy array or python list
        if hasattr(emb, 'shape'):
            # numpy array
            if len(emb.shape) != 2:
                return None
            vec = emb[0].tolist()
        else:
            # python list: expect list of lists [[...]]
            try:
                if isinstance(emb[0], list) or isinstance(emb[0], tuple):
                    vec = list(emb[0])
                else:
                    # single flat vector
                    vec = list(emb)
            except Exception:
                return None
        if len(vec) != self.vector_dim:
            logger.warning("Embedding dimension %s does not match expected %s", len(vec), self.vector_dim)
            return None
        # Query act_embeddings using pgvector distance operator. We expect embedding <=> $1 to return cosine distance (0..2)
        # We'll compute similarity = 1 - distance; require similarity >= threshold
        # pass vector as Postgres vector literal string and cast to vector in SQL
        vec_param = '[' + ','.join(str(float(x)) for x in vec) + ']'
        sql = """
        SELECT act_id, text_represented, embedding <=> %s::vector AS distance
        FROM act_embeddings
        ORDER BY embedding <=> %s::vector ASC
        LIMIT %s
        """
        cur = self.conn.cursor()
        try:
            cur.execute(sql, (vec_param, vec_param, top_k))
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else []
        except Exception as e:
            logger.error("Vector search failed: %s", e)
            return None
        if not rows:
            return None
        best = None
        for r in rows:
            # map to dict if needed
            if isinstance(r, dict):
                rowd = r
            else:
                rowd = dict(zip(cols, r)) if cols else {}
            dist = float(rowd.get('distance') if rowd.get('distance') is not None else rowd.get('distance'))
            sim = 1.0 - dist
            # ensure sim in [0,1]
            sim = max(0.0, min(1.0, sim))
            if sim >= threshold:
                best = (rowd.get('act_id'), sim, rowd.get('text_represented'))
                break
        if not best:
            return None
        act_id, sim, txt = best
        return {"id": act_id, "confidence": round(sim, 3), "method": "vector", "score": sim, "text_represented": txt}

    def resolve_citation(self, parsed_ner: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a parsed NER citation dict to a legal act id.

        parsed_ner may contain keys:
          - publisher (str)
          - year (int)
          - position (int)
          - citation_text (str)  (the textual span that names the act)

        Returns dict with keys: id, confidence, method, and optional debug info.
        """
        # Resolve citations in priority order: exact, fuzzy, then semantic embedding fallback.
        publisher = parsed_ner.get('publisher')
        year = parsed_ner.get('year')
        position = parsed_ner.get('position')
        text = parsed_ner.get('citation_text') or parsed_ner.get('title') or parsed_ner.get('text')

        # 1) Exact match
        exact = self._exact_match(publisher, year, position)
        if exact:
            exact['matched_by'] = {'publisher': publisher, 'year': year, 'position': position}
            return exact

        # 2) Fuzzy / alias
        fuzzy = self._fuzzy_alias_match(text or "")
        if fuzzy:
            fuzzy['matched_by_text'] = text
            return fuzzy

        # 3) Vector match
        vector = self._vector_match(text or "")
        if vector:
            vector['matched_by_text'] = text
            return vector

        return {"id": None, "confidence": 0.0, "method": "none"}


if __name__ == '__main__':
    # small interactive demo (requires psycopg2 and optionally sentence-transformers)
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--db-url', required=True)
    p.add_argument('--text', help='Citation text to resolve')
    p.add_argument('--publisher')
    p.add_argument('--year', type=int)
    p.add_argument('--position', type=int)
    p.add_argument('--embed-model', help='Optional sentence-transformers model')
    args = p.parse_args()
    linker = LegalEntityLinker(args.db_url, embed_model_name=args.embed_model)
    qry = {'publisher': args.publisher, 'year': args.year, 'position': args.position, 'citation_text': args.text}
    print(linker.resolve_citation(qry))
    linker.close()
