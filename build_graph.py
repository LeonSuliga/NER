"""
Load normalized staging JSONL into Neo4j graph.

Creates nodes:
  (:LegalAct {id, title, publisher, year, position, act_type, status})
  Optionally creates article templates (:Article {id, number}) for each act (flag --create-article-templates)

Creates relationships:
  (:LegalAct)-[:AMENDS]->(:LegalAct)
  (:LegalAct)-[:REPEALS]->(:LegalAct)
  (:LegalAct)-[:HAS_STRUCTURE]->(:Article)

Usage:
  python build_graph.py --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-pass secret --staging-dir ./staging

Note: ensure constraints.cypher has been applied or allow script to apply it.
"""
import os
import glob
import json
import argparse
import logging
from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("build_graph")

DEFAULT_STAGING = os.path.join(os.path.dirname(__file__), "staging")
CONSTRAINTS_FILE = os.path.join(os.path.dirname(__file__), "constraints.cypher")


def find_staging_files(staging_dir: str) -> List[str]:
    patterns = [os.path.join(staging_dir, "*.jsonl"), os.path.join(staging_dir, "*.ndjson")]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))
    return sorted(files)


def load_constraints(driver, path: str):
    if not os.path.exists(path):
        logger.warning("Constraints file not found: %s", path)
        return
    with open(path, 'r', encoding='utf-8') as fh:
        cypher = fh.read()
    logger.info("Applying constraints/indexes from %s", path)
    with driver.session() as session:
        for stmt in [s.strip() for s in cypher.split(';') if s.strip()]:
            try:
                session.run(stmt)
            except Exception as e:
                logger.error("Failed to run constraint statement: %s -> %s", stmt, e)
    logger.info("Constraints applied (best-effort)")


def batch_upsert_acts(driver, acts: List[Dict[str, Any]], batch_size: int = 200):
    # Merge each legal act into a unique Neo4j node keyed by the official act ID.
    logger.info("Upserting %d acts into Neo4j", len(acts))
    with driver.session() as session:
        for i in range(0, len(acts), batch_size):
            batch = acts[i:i+batch_size]
            # Use UNWIND for batch MERGE
            cypher = """
            UNWIND $rows AS r
            MERGE (a:LegalAct {id: r.id})
            SET a.title = r.title,
                a.publisher = r.publisher,
                a.year = r.year,
                a.position = r.position,
                a.act_type = r.act_type,
                a.status = r.status,
                a.raw = r.raw
            """
            session.run(cypher, rows=batch)
    logger.info("Upserted acts")


def create_article_templates(driver, act_ids: List[str], templates_per_act: int = 0, batch_size: int = 200):
    # Create empty article templates for future paragraph-level legal parsing.
    if templates_per_act <= 0:
        return
    logger.info("Creating %d article templates per act for %d acts", templates_per_act, len(act_ids))
    with driver.session() as session:
        for i in range(0, len(act_ids), batch_size):
            batch_ids = act_ids[i:i+batch_size]
            rows = []
            for aid in batch_ids:
                for n in range(1, templates_per_act+1):
                    art_id = f"{aid}#art_{n}"
                    rows.append({"act_id": aid, "art_id": art_id, "number": str(n)})
            cypher = """
            UNWIND $rows AS r
            MERGE (art:Article {id: r.art_id})
            SET art.number = r.number
            WITH art, r
            MATCH (a:LegalAct {id: r.act_id})
            MERGE (a)-[:HAS_STRUCTURE]->(art)
            """
            session.run(cypher, rows=rows)
    logger.info("Article templates created")


def extract_relations(item_raw: Dict[str, Any]) -> Dict[str, List[str]]:
    """Try to extract relation targets (act ids/addresses) from normalized record's 'relations' or 'raw' fields."""
    # Flatten relation payloads into a normalized map keyed by the graph edge type.
    out = {"amends": [], "repeals": [], "others": []}
    relations = item_raw.get('relations') or {}
    # relations may be dict of lists or lists
    for key, val in relations.items():
        if not val:
            continue
        # normalize to list
        vals = val if isinstance(val, list) else [val]
        for entry in vals:
            # entry might be string address or dict with 'address' or 'id'
            target = None
            if isinstance(entry, str):
                target = entry
            elif isinstance(entry, dict):
                target = entry.get('address') or entry.get('id') or entry.get('uri')
            if target:
                target = str(target)
                if key.lower() in ('changes', 'amendments', 'amends', 'changes_to', 'zmiany'):
                    out['amends'].append(target)
                elif key.lower() in ('repeals', 'uchylone', 'uchyla') or key.lower().startswith('repeal'):
                    out['repeals'].append(target)
                else:
                    out['others'].append(target)
    # also check raw.references
    raw = item_raw.get('raw') or {}
    if isinstance(raw, dict) and raw.get('references'):
        refs = raw.get('references')
        vals = refs if isinstance(refs, list) else [refs]
        for r in vals:
            if isinstance(r, dict):
                t = r.get('address') or r.get('id')
            else:
                t = r
            if t:
                out['others'].append(t)
    # normalize addresses to simple ids if they look like '/eli/acts/...'
    def simplify(addr: str) -> str:
        s = str(addr)
        if s.startswith('/eli/'):
            parts = s.strip('/').split('/')
            # expect /eli/acts/<publisher>/<year>/<position>
            if len(parts) >= 5:
                return parts[3] + parts[4] + (parts[5] if len(parts) > 5 else '')
        return s
    for k in list(out.keys()):
        out[k] = [simplify(x) for x in out[k]]
    return out


def create_relations(driver, acts: List[Dict[str, Any]], batch_size: int = 200):
    # Materialize the graph edges for amendment and repeal links using the staged relation metadata.
    logger.info("Creating relations (AMENDS/REPEALS) based on staging relations field")
    relationships = []  # tuples (src, reltype, tgt)
    for item in acts:
        src = item.get('id') or item.get('address')
        if not src:
            continue
        rels = extract_relations(item)
        for tgt in rels.get('amends', []):
            relationships.append((src, 'AMENDS', tgt))
        for tgt in rels.get('repeals', []):
            relationships.append((src, 'REPEALS', tgt))
        for tgt in rels.get('others', []):
            relationships.append((src, 'REFERENCES', tgt))

    logger.info("Found %d candidate relationships", len(relationships))
    with driver.session() as session:
        for i in range(0, len(relationships), batch_size):
            batch = relationships[i:i+batch_size]
            rows = [{'src': s, 'rel': r, 'tgt': t} for (s, r, t) in batch]
            cypher = """
            UNWIND $rows AS r
            MATCH (a:LegalAct {id: r.src})
            MATCH (b:LegalAct {id: r.tgt})
            WHERE a IS NOT NULL AND b IS NOT NULL
            CALL apoc.merge.relationship(a, r.rel, {}, {}, b) YIELD rel
            RETURN count(rel) AS created
            """
            # Note: using apoc.merge.relationship for idempotent relationship create. If APOC not available, fallback to MERGE
            try:
                session.run(cypher, rows=rows)
            except Exception as e:
                logger.warning("APOC not available or failed: falling back to MERGE (%s)", e)
                cy = """
                UNWIND $rows AS r
                MATCH (a:LegalAct {id: r.src})
                MATCH (b:LegalAct {id: r.tgt})
                MERGE (a)-[rel:`%s`]->(b)
                RETURN count(rel) as created
                """
                # cy needs formatting per relation; fall back to per-relation run
                for rel_name in set([r['rel'] for r in rows]):
                    filt = [r for r in rows if r['rel'] == rel_name]
                    session.run("""
                    UNWIND $f AS r
                    MATCH (a:LegalAct {id: r.src})
                    MATCH (b:LegalAct {id: r.tgt})
                    MERGE (a)-[rel:%s]->(b)
                    RETURN count(rel) as created
                    """ % rel_name, f=filt)
    logger.info("Relations creation attempted")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--neo4j-uri', required=True)
    p.add_argument('--neo4j-user', required=True)
    p.add_argument('--neo4j-pass', required=True)
    p.add_argument('--staging-dir', default=DEFAULT_STAGING)
    p.add_argument('--batch-size', type=int, default=200)
    p.add_argument('--create-article-templates', type=int, default=0,
                   help='Optional: create N article templates per act (default 0)')
    args = p.parse_args()

    files = find_staging_files(args.staging_dir)
    if not files:
        logger.error("No staging files found in %s", args.staging_dir)
        return

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_pass))

    # apply constraints
    load_constraints(driver, CONSTRAINTS_FILE)

    # read all records into memory in batches per file
    all_act_ids = []
    for path in files:
        acts = []
        with open(path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                # ensure minimal fields
                rec_min = {
                    'id': rec.get('id') or rec.get('address'),
                    'title': rec.get('title') or (rec.get('raw') or {}).get('title') or '',
                    'publisher': rec.get('publisher') or '',
                    'year': rec.get('year'),
                    'position': rec.get('position'),
                    'act_type': rec.get('type') or rec.get('act_type'),
                    'status': rec.get('status'),
                    # store raw as JSON string to avoid complex nested types not allowed as Neo4j properties
                    'raw': json.dumps(rec.get('raw') or rec, ensure_ascii=False),
                    'relations': rec.get('relations') or {}
                }
                if rec_min['id']:
                    acts.append(rec_min)
                    all_act_ids.append(rec_min['id'])
        if acts:
            batch_upsert_acts(driver, acts, batch_size=args.batch_size)
            create_relations(driver, acts, batch_size=args.batch_size)

    # optional article templates
    if args.create_article_templates > 0:
        create_article_templates(driver, all_act_ids, templates_per_act=args.create_article_templates, batch_size=args.batch_size)

    driver.close()
    logger.info("Graph build complete")


if __name__ == '__main__':
    main()
