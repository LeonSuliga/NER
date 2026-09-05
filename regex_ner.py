import re
from typing import Dict, Any, Optional

# Basic regex-based extractor for legal citations in Polish text.
# Returns dict compatible with entity_linker.resolve_citation input.

PUB_PATTERNS = [
    (re.compile(r'\bDz\.?\s*U\.?\b', re.I), 'DU'),
    (re.compile(r'\bDziennik\s+Ustaw\b', re.I), 'DU'),
    (re.compile(r'\bM\.P\.?\b', re.I), 'MP'),
    (re.compile(r'\bMonitor\s+Polski\b', re.I), 'MP'),
]

YEAR_RE = re.compile(r"(19|20)\d{2}")
POSIT_RE = re.compile(r"poz\.\s*(\d+)|p\.\s*(\d+)|poz\s*(\d+)", re.I)
PINPOINT_RE = re.compile(r"(art\.?\s*\d+[a-z0-9\-a]*)((?:\s*(ust\.?|pkt|pkt)\.?\s*\d+[a-z0-9\-]*)*)", re.I)
LAW_TITLE_IN_PARENS = re.compile(r"\(([^)]+)\s*(?:Dz\.|M\.P\.|z)\s*\d{4}")
LAW_TITLE_SIMPLE = re.compile(r"(?:ustawy|ustawa|rozporządzenia|rozporządzenie|kodeksu|kodeks)\s+([A-ZĄĘŁŃÓŚŻŹa-ząćęłńóśżź\s\-]+)", re.I)

# patterns to find publisher mentions and nearby publication year
PUB_NEAR_RE = re.compile(r"(Dz\.?\s*U\.?|Dziennik\s+Ustaw|M\.P\.?|Monitor\s+Polski)\s*[,\(\s\w\.,]*?(\d{4})", re.I)
PUB_SHORT_RE = re.compile(r"(Dz\.?\s*U\.?|D\.U\.|M\.P\.?|Dziennik\s+Ustaw|Monitor\s+Polski)", re.I)


def extract_publisher(text: str) -> Optional[str]:
    # Extract the publisher code from legal references such as Dz.U. or M.P.
    for pat, code in PUB_PATTERNS:
        if pat.search(text):
            return code
    return None


def extract_act_year(text: str) -> Optional[int]:
    # Extract act enactment year from phrases like 'z dnia 23 kwietnia 1964 r.'
    m = re.search(r"z\s+dnia[^\d]{0,30}?((19|20)\d{2})\s*r\.?", text, re.I)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    # fallback: any year
    m2 = YEAR_RE.search(text)
    if m2:
        try:
            return int(m2.group(0))
        except Exception:
            return None
    return None


def extract_pub_year(text: str) -> Optional[int]:
    # Extract publication year near the publisher tokens; this is the value used for linker matching.
    m = PUB_NEAR_RE.search(text)
    if m:
        try:
            return int(m.group(2))
        except Exception:
            pass
    # look for patterns like 'Dz. U. z 2020 r.' or 'Dz. U. 2020 poz.'
    m2 = re.search(r"Dz\.?\s*U\.?\s*(?:z\s*)?(\d{4})", text, re.I)
    if m2:
        try:
            return int(m2.group(1))
        except Exception:
            pass
    m3 = re.search(r"M\.P\.?.*?(\d{4})", text, re.I)
    if m3:
        try:
            return int(m3.group(1))
        except Exception:
            pass
    return None


def extract_position(text: str) -> Optional[int]:
    m = POSIT_RE.search(text)
    if m:
        for g in m.groups():
            if g:
                try:
                    return int(g)
                except Exception:
                    pass
    # sometimes format like 'poz. 1)' or 'poz.1,' handled above
    return None


def extract_pinpoint(text: str) -> Optional[str]:
    m = PINPOINT_RE.search(text)
    if m:
        return m.group(0)
    return None


def extract_law_title(text: str) -> Optional[str]:
    # try parentheses
    m = re.search(r"\(([^)]+)\)", text)
    if m:
        candidate = m.group(1)
        parts = re.split(r"[,;]", candidate)
        for p in parts:
            p = p.strip()
            if len(p) > 3 and any(c.isalpha() for c in p):
                if not re.search(r"Dz\.?\s*U\.?|M\.P\.?|poz\.|\d{4}", p, re.I):
                    return p
    m2 = LAW_TITLE_SIMPLE.search(text)
    if m2:
        return m2.group(1).strip()
    return None


def parse(text: str) -> Dict[str, Any]:
    """Return dict with keys: publisher (code), year (int), position (int), pinpoint (str), citation_text (str), law_title (str)

    year in the output is set to pub_year if available, otherwise act_year.
    Additionally both act_year and pub_year are included in the returned dict.
    """
    # Prefer publication year when attached to Dz.U./M.P., while preserving the act year as metadata.
    out = {'publisher': None, 'year': None, 'act_year': None, 'pub_year': None, 'position': None, 'pinpoint': None, 'citation_text': text, 'law_title': None}
    txt = text
    out['publisher'] = extract_publisher(txt)
    out['act_year'] = extract_act_year(txt)
    out['pub_year'] = extract_pub_year(txt)
    out['position'] = extract_position(txt)
    out['pinpoint'] = extract_pinpoint(txt)
    out['law_title'] = extract_law_title(txt)

    # prefer pub_year near publisher tokens; fall back to act_year
    if out['pub_year'] is not None:
        out['year'] = out['pub_year']
    elif out['act_year'] is not None:
        out['year'] = out['act_year']
    else:
        out['year'] = None

    # if publisher missing but law_title contains 'Dz.U.' style, map
    if out['publisher'] is None and out['law_title']:
        if 'Dz.' in out['law_title'] or 'DzU' in out['law_title']:
            out['publisher'] = 'DU'
    # normalize ints
    try:
        out['year'] = int(out['year']) if out['year'] is not None else None
    except Exception:
        out['year'] = None
    try:
        out['position'] = int(out['position']) if out['position'] is not None else None
    except Exception:
        out['position'] = None
    return out


if __name__ == '__main__':
    # quick demo
    samples = [
        "Na podstawie art. 5 ust. 2 ustawy z dnia 23 kwietnia 1964 r. - Kodeks cywilny (Dz. U. z 2020 r. poz. 1) orzeka się...",
        "Zgodnie z Rozporządzeniem Ministra Finansów z dnia 23 grudnia 2019 r. (Dz. U. 2020 poz. 2) stosuje się...",
        "Powołując się na art. 12 ustawy Prawo o ruchu drogowym (Dziennik Ustaw z 2018 r., poz. 100)"
    ]
    for s in samples:
        print(s)
        print(parse(s))
        print('---')
