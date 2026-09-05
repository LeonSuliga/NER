"""
ETL module for fetching legal acts from Sejm ELI API.
Saves normalized records to staging JSONL files under ./staging/

Usage examples:
  python etl_sejm.py --publisher dziennik_ustaw --start-year 2018 --end-year 2020
  python etl_sejm.py --publisher monitor_polski --year 2021

Notes:
- Publisher values: 'dziennik_ustaw' (DU) and 'monitor_polski' (MP) by default.
- The script uses exponential backoff retries (tenacity) and respects 429 Retry-After when present.
"""
import os
import sys
import time
import json
import logging
from typing import Dict, Any, Iterator, List, Optional
import argparse

import urllib.request
import urllib.parse
from urllib.error import HTTPError, URLError
import random
import ssl


# simple retry/backoff parameters (no external deps)
MAX_RETRIES = 5
BACKOFF_FACTOR = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("etl_sejm")

API_BASE = "https://api.sejm.gov.pl/eli/acts"
STAGING_DIR = os.path.join(os.path.dirname(__file__), "staging")
os.makedirs(STAGING_DIR, exist_ok=True)


class SejmETL:
    def __init__(self, per_page: int = 100, pause: float = 0.15, insecure: bool = False):
        # Configure HTTP client for Sejm ELI access with retries and optional SSL bypass.
        self.per_page = per_page
        self.pause = pause
        self.insecure = insecure

    def _get(self, url: str, params: Dict[str, Any] = None, timeout: int = 30):
        """Perform a GET request with retries and exponential backoff. Returns object with .json() and .headers."""
        # Retry HTTP requests with exponential backoff to handle 429 and transient failures.
        query = ""
        if params:
            try:
                query = "?" + urllib.parse.urlencode(params)
            except Exception:
                query = "?" + "&".join(f"{k}={v}" for k, v in (params.items() if isinstance(params, dict) else []))
        full = url + query
        attempts = 0
        backoff = 1.0
        while attempts < MAX_RETRIES:
            try:
                logger.debug("GET attempt %d for %s", attempts + 1, full)
                req = urllib.request.Request(full, headers={"User-Agent": "SejmETL/1.0"})
                ctx = ssl._create_unverified_context() if getattr(self, 'insecure', False) else None
                if ctx is not None:
                    resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
                else:
                    resp = urllib.request.urlopen(req, timeout=timeout)
                status = resp.getcode()
                body = resp.read()
                headers = {k: v for k, v in resp.getheaders()} if hasattr(resp, 'getheaders') else {}
                if status == 429:
                    ra = headers.get("Retry-After")
                    try:
                        wait_sec = int(ra) if ra is not None else 10
                    except Exception:
                        wait_sec = 10
                    logger.warning("Rate limited: 429 - sleeping for %s seconds", wait_sec)
                    time.sleep(wait_sec)
                    raise URLError("429")
                if status >= 400:
                    raise HTTPError(full, status, f"HTTP {status}", headers, None)
                import json as _json
                data = _json.loads(body.decode('utf-8')) if body else None

                class _Resp:
                    def __init__(self, data, headers, status_code):
                        self._data = data
                        self.headers = headers
                        self.status_code = status_code

                    def json(self):
                        return self._data

                return _Resp(data, headers, status)
            except (HTTPError, URLError, ValueError) as e:
                attempts += 1
                sleep_time = backoff + random.random()
                logger.warning("GET failed %s (attempt %d/%d): %s; retrying in %.1fs", full, attempts, MAX_RETRIES, e, sleep_time)
                time.sleep(sleep_time)
                backoff *= BACKOFF_FACTOR
        raise Exception(f"Max retries exceeded for URL: {full}")

    def fetch_list(self, publisher: str, year: Optional[int] = None, limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Fetch list of acts for publisher and optional year.
        If the API returns publisher summaries instead of act entries, fall back to fetching details by position using publisher codes (DU/MP).
        """
        # Walk publisher pages and fall back to direct detail fetch when the API returns summary objects.
        publisher_map = {
            'dziennik_ustaw': 'DU',
            'monitor_polski': 'MP',
            'DU': 'DU',
            'MP': 'MP'
        }
        # Try standard listing first
        page = 1
        yielded = 0
        while True:
            params = {"publisher": publisher, "page": page, "per_page": self.per_page}
            if year:
                params["year"] = year
            url = API_BASE
            try:
                resp = self._get(url, params=params)
            except Exception as e:
                logger.error("Failed to fetch list page %s: %s", page, e)
                break
            data = resp.json()
            if not isinstance(data, list) or len(data) == 0:
                break
            # detect publisher-summary entries (they contain 'code' and 'years')
            first = data[0]
            if isinstance(first, dict) and ('code' in first and 'years' in first):
                logger.info("API returned publisher summary; falling back to per-position detail fetch using publisher map")
                publisher_code = publisher_map.get(publisher, publisher)
                if year is None:
                    logger.error("Year required for per-position fallback")
                    break
                # yield detailed items by incrementing position
                for detail in self.fetch_by_position(publisher_code, year, limit=limit):
                    yielded += 1
                    yield detail
                    if limit and yielded >= limit:
                        return
                return
            logger.info("Fetched page %s (items=%s) for publisher=%s year=%s", page, len(data), publisher, year)
            for item in data:
                yield item
                yielded += 1
                if limit and yielded >= limit:
                    return
            page += 1
            time.sleep(self.pause)

    def fetch_by_position(self, publisher_code: str, year: int, limit: Optional[int] = None, max_consecutive_missing: int = 100) -> Iterator[Dict[str, Any]]:
        """Iterate position=1.. and fetch detail endpoint /eli/acts/{publisher_code}/{year}/{position}.
        Stop when collected `limit` items or when `max_consecutive_missing` consecutive 404s are encountered.
        """
        # Probe act positions sequentially until the API stops returning valid records.
        pos = 1
        collected = 0
        missing = 0
        while True:
            if limit and collected >= limit:
                return
            url = f"{API_BASE}/{publisher_code}/{year}/{pos}"
            try:
                resp = self._get(url)
                detail = resp.json()
                missing = 0
                collected += 1
                yield detail
            except Exception as e:
                # treat as missing (404 etc.)
                missing += 1
                logger.debug("Detail missing for %s pos=%s: %s", publisher_code, pos, e)
                if missing >= max_consecutive_missing:
                    logger.info("Reached %s consecutive missing positions; stopping iteration", max_consecutive_missing)
                    return
            pos += 1
            time.sleep(self.pause)

    def fetch_detail(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch full detail for a list item. Attempts to use 'uri' or 'links' information if available.
        Falls back to constructing detail URL from address if possible."""
        # Construct the canonical detail URL from address or links when the list payload is sparse.
        detail_url = None
        if item.get("uri"):
            detail_url = item["uri"]
        # sometimes API returns 'links' with 'self'
        links = item.get("links") or {}
        if isinstance(links, dict) and links.get("self"):
            detail_url = links.get("self")
        # fallback: build from address like '/eli/acts/dziennik_ustaw/2020/1'
        address = item.get("address")
        if not detail_url and address:
            # address can be like 'DU/2020/1' or '/eli/acts/dziennik_ustaw/2020/1'
            if address.startswith("/eli/"):
                detail_url = f"https://api.sejm.gov.pl{address}"
            else:
                # try splitting
                parts = address.strip('/').split('/')
                if len(parts) >= 3:
                    # assume publisher/year/position
                    pub = parts[0]
                    year = parts[1]
                    pos = parts[2]
                    detail_url = f"{API_BASE}/{pub}/{year}/{pos}"
        if not detail_url:
            logger.warning("No detail URL could be determined for item: %s", item.get("id") or item.get("address"))
            return None
        try:
            resp = self._get(detail_url)
            return resp.json()
        except Exception as e:
            logger.error("Failed to fetch detail for %s: %s", detail_url, e)
            return None

    @staticmethod
    def normalize_act(detail: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize fields to a compact dictionary for staging.
        This is resilient to missing keys in API responses.
        """
        # Normalize heterogeneous API payloads into one staging record with stable keys.
        address = detail.get("address") or detail.get("id") or detail.get("eli")
        title = detail.get("title") or detail.get("name") or ""
        act_type = detail.get("type") or detail.get("documentType") or ""
        publisher = detail.get("publisher") or detail.get("source") or ""
        year = None
        position = None
        # try to extract from address like 'DU/2020/1' or 'dziennik_ustaw/2020/1'
        if address:
            s = address.strip('/')
            parts = s.split('/')
            # find first numeric part as year
            for i, p in enumerate(parts):
                if p.isdigit() and len(p) == 4:
                    year = int(p)
                    if i+1 < len(parts) and parts[i+1].isdigit():
                        position = int(parts[i+1])
                    break
        # status may be nested
        status = detail.get("status") or detail.get("legalState") or None

        # gather relations/links: changes, repeals, consolidated_with, etc.
        relations = {}
        for key in ["changes", "amendments", "repeals", "replacedBy", "replaces", "relations"]:
            if key in detail:
                relations[key] = detail[key]
        # unify references if available under 'references'
        if detail.get("references"):
            relations.setdefault("references", detail.get("references"))

        normalized = {
            "address": address,
            "id": detail.get("id") or address,
            "title": title,
            "type": act_type,
            "publisher": publisher,
            "year": year,
            "position": position,
            "status": status,
            "relations": relations,
            "raw": detail,
        }
        return normalized

    def run(self, publisher: str, start_year: Optional[int] = None, end_year: Optional[int] = None, out_file: Optional[str] = None, limit: Optional[int] = None):
        # Stream each fetched act directly to JSONL to avoid large in-memory batches.
        if not out_file:
            out_file = os.path.join(STAGING_DIR, f"staging_{publisher}.jsonl")
        logger.info("Starting ETL for publisher=%s years=%s..%s -> %s (limit=%s)", publisher, start_year, end_year, out_file, limit)
        written = 0
        with open(out_file, 'a', encoding='utf-8') as fh:
            years = [start_year] if start_year and not end_year else list(range(start_year, end_year+1)) if start_year and end_year else [None]
            for year in years:
                for item in self.fetch_list(publisher=publisher, year=year):
                    if limit is not None and written >= limit:
                        logger.info("Reached limit=%s, stopping", limit)
                        return
                    try:
                        detail = self.fetch_detail(item) or item
                        norm = self.normalize_act(detail)
                        fh.write(json.dumps(norm, ensure_ascii=False) + "\n")
                        written += 1
                        logger.info("[OK] Saved id=%s title=%s", norm.get('id'), (norm.get('title') or '')[:80])
                    except Exception as e:
                        logger.error("[ERROR] Failed processing item %s: %s", item.get('id') or item.get('address'), e)
                    if written % 50 == 0 and written > 0:
                        logger.info("Written %s records so far", written)
        logger.info("ETL finished, total written=%s", written)


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--publisher', required=True, help="Publisher key, e.g. dziennik_ustaw or monitor_polski")
    p.add_argument('--start-year', type=int, help="Start year (inclusive)")
    p.add_argument('--end-year', type=int, help="End year (inclusive)")
    p.add_argument('--year', type=int, help="Single year, alternative to start/end")
    p.add_argument('--out', help="Output staging file path (optional)")
    p.add_argument('--insecure', action='store_true', help='Disable SSL verification (useful for testing)')
    p.add_argument('--per-page', type=int, default=100, help='Number of items per page when paginating')
    p.add_argument('--limit', type=int, help='Optional limit on number of acts to fetch (for testing)')
    return p.parse_args()


def main():
    args = _parse_args()
    if args.year and (args.start_year or args.end_year):
        logger.error("Use either --year or --start-year/--end-year, not both")
        sys.exit(2)
    etl = SejmETL(per_page=args.per_page, insecure=args.insecure)
    if args.year:
        etl.run(args.publisher, start_year=args.year, end_year=args.year, out_file=args.out, limit=args.limit)
    else:
        etl.run(args.publisher, start_year=args.start_year, end_year=args.end, out_file=args.out, limit=args.limit)


if __name__ == '__main__':
    main()
