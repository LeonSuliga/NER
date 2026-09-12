import re
import json
from pathlib import Path

# Article references
ART_PATTERN = re.compile(
    r'\bart\.\s*\d+[a-z]*'
    r'(?:\s*(?:,|i|oraz|-|–)\s*\d+[a-z]?)*',
    re.IGNORECASE
)

# Paragraph references
PAR_PATTERN = re.compile(
    r'§\s*\d+[a-z]*'
    r'(?:\s*(?:,|i|oraz|-|–)\s*\d+[a-z]?)*',
    re.IGNORECASE
)

# Subsection references
UST_PATTERN = re.compile(
    r'\bust\.\s*\d+[a-z]*'
    r'(?:\s*(?:,|i|oraz|-|–)\s*\d+[a-z]?)*',
    re.IGNORECASE
)

# Point references
PKT_PATTERN = re.compile(
    r'\bpkt\.?\s*\d+[a-z]*'
    r'(?:\s*(?:,|i|oraz|-|–)\s*\d+[a-z]?)*',
    re.IGNORECASE
)

# Letter references
LIT_PATTERN = re.compile(
    r'\blit\.\s*[a-z]+'
    r'(?:\s*(?:,|i|oraz|-|–)\s*[a-z]+)*',
    re.IGNORECASE
)

ORDINALS = (
    r'pierwszym|pierwszego|pierwsze|pierwszy|'
    r'drugiego|drugie|drugim|drugi|'
    r'trzeciego|trzecim|trzecie|trzeci|'
    r'czwartym|czwartego|czwarte|czwarty|'
    r'piątym|piątego|piąte|piąty|'
    r'szóstym|szóstego|szóste|szósty|'
    r'siódmym|siódmego|siódme|siódmy|'
    r'ósmym|ósmego|ósme|ósmy|'
    r'dziewiątym|dziewiątego|dziewiąte|dziewiąty|'
    r'dziesiątym|dziesiątego|dziesiąte|dziesiąty'
)

# TIRET
TIR_PATTERN = re.compile(
    rf'\btiret\s+(?:{ORDINALS})'
    rf'(?:\s*(?:,|i|oraz)\s*(?:{ORDINALS}))*',   
    re.IGNORECASE
)

# PODWÓJNY TIRET
PODW_TIR_PATTERN = re.compile(
    rf'\bpodwójne\s+tiret\s+(?:{ORDINALS})'
    rf'(?:\s*(?:,|i|oraz)\s*(?:{ORDINALS}))*',
    re.IGNORECASE
)

# ZDANIE
ZDA_PATTERN = re.compile(
    rf'\b(?:zdanie|zdania|zdaniu|zdaniem)\s+'
    rf'(?:{ORDINALS})'
    rf'(?:\s*(?:,|i|oraz)\s*(?:{ORDINALS}))*',
    re.IGNORECASE
)

# PUBLIKATORY 

# DZIENNIK USTAW 
DU_PATTERN = re.compile(
    r'\bDz\.\s*U\.'
    r'(?:\s+z\s+\d{4}\s+r\.)?'
    r'\s+poz\.\s*\d+'
    r'(?:\s*(?:,|i|oraz)\s*\d+)*'
    r'(?:'
        r'\s*(?:,|i|oraz)?\s*'
        r'z\s+\d{4}\s+r\.'
        r'\s+poz\.\s*\d+'
        r'(?:\s*(?:,|i|oraz)\s*\d+)*'
    r')*',
    re.IGNORECASE
)

# MONITOR POLSKI
MP_PATTERN = re.compile(
    r'\bM\.\s*P\.'
    r'(?:\s+z\s+\d{4}\s+r\.)?'
    r'\s+poz\.\s*\d+'
    r'(?:\s*(?:,|i|oraz)\s*\d+)*'
    r'(?:'
        r'\s*(?:,|i|oraz)?\s*'
        r'z\s+\d{4}\s+r\.'
        r'\s+poz\.\s*\d+'
        r'(?:\s*(?:,|i|oraz)\s*\d+)*'
    r')*',
    re.IGNORECASE
)

# DZIENNIK URZĘDOWY UE
DUE_PATTERN = re.compile(
    r'\bDz\.\s*Urz\.\s*UE\s+'
    r'[LC]\s+\d+'
    r'\s+z\s+\d{2}\.\d{2}\.\d{4}'
    r',\s*str\.\s*\d+',
    re.IGNORECASE
)

# DZIENNIK URZĘDOWY WE
DWE_PATTERN = re.compile(
    r'\bDz\.\s*Urz\.\s*WE\s+'
    r'[LC]\s+\d+'
    r'\s+z\s+\d{2}\.\d{2}\.\d{4}'
    r',\s*str\.\s*\d+',
    re.IGNORECASE
)

def add_entity(entities, start, end, text, label):
    """Append one Label Studio-compatible entity annotation."""
    entities.append(
        {
            "from_name": "label",
            "to_name": "text",
            "type": "labels",
            "value": {
                "start": start,
                "end": end,
                "text": text,
                "labels": [label]
            }
        }
    )


def process_reference(
    text,
    match,
    reference_type,
    key_pattern,
    value_pattern
):
    """Create separate annotations for a reference key and its values."""
    entities = []

    reference_text = match.group()
    reference_start = match.start()

    key_match = key_pattern.search(reference_text)

    if not key_match:
        return entities

    key_start = reference_start + key_match.start()
    key_end = reference_start + key_match.end()

    add_entity(
        entities,
        key_start,
        key_end,
        text[key_start:key_end],
        f"{reference_type}_KEY"
    )

    value_start = key_match.end()

    for value_match in value_pattern.finditer(
        reference_text,
        value_start
    ):
        start = reference_start + value_match.start()
        end = reference_start + value_match.end()

        add_entity(
            entities,
            start,
            end,
            text[start:end],
            f"{reference_type}_VAL"
        )

    return entities


def process_du_mp_publication(text, match):
    """Annotate the publication key and every position number it contains."""
    entities = []

    publication_text = match.group()
    publication_start = match.start()

    part_pattern = re.compile(
        r'(?:'
            r'\bDz\.\s*U\.'
            r'(?:\s+z\s+\d{4}\s+r\.)?'
            r'\s+poz\.'
        r'|'
            r'\bM\.\s*P\.'
            r'(?:\s+z\s+\d{4}\s+r\.)?'
            r'\s+poz\.'
        r'|'
            r'\bz\s+\d{4}\s+r\.'
            r'\s+poz\.'
        r')'
        r'\s*\d+'
        r'(?:\s*(?:,|i|oraz)\s*\d+)*',
        re.IGNORECASE
    )

    for part_match in part_pattern.finditer(
        publication_text
    ):

        part_text = part_match.group()

        part_start = (
            publication_start +
            part_match.start()
        )

        key_pattern = re.compile(
            r'(?:'
                r'\bDz\.\s*U\.'
                r'(?:\s+z\s+\d{4}\s+r\.)?'
                r'\s+poz\.'
            r'|'
                r'\bM\.\s*P\.'
                r'(?:\s+z\s+\d{4}\s+r\.)?'
                r'\s+poz\.'
            r'|'
                r'\bz\s+\d{4}\s+r\.'
                r'\s+poz\.'
            r')',
            re.IGNORECASE
        )

        key_match = key_pattern.search(part_text)

        if not key_match:
            continue

        key_start = part_start + key_match.start()
        key_end = part_start + key_match.end()

        add_entity(
            entities,
            key_start,
            key_end,
            text[key_start:key_end],
            "PUB_KEY"
        )

        value_pattern = re.compile(r'\d+')

        value_start = key_match.end()

        for value_match in value_pattern.finditer(
            part_text,
            value_start
        ):
            start = part_start + value_match.start()
            end = part_start + value_match.end()

            add_entity(
                entities,
                start,
                end,
                text[start:end],
                "PUB_VAL"
            )

    return entities

def process_eu_publication(text, match):

    entities = []

    publication_text = match.group()
    publication_start = match.start()

    key_pattern = re.compile(
        r'\bDz\.\s*Urz\.\s*(?:UE|WE)\s+'
        r'[LC]\s+\d+'
        r'\s+z\s+\d{2}\.\d{2}\.\d{4}'
        r',\s*str\.',
        re.IGNORECASE
    )

    key_match = key_pattern.search(
        publication_text
    )

    if not key_match:
        return entities

    key_start = (
        publication_start +
        key_match.start()
    )

    key_end = (
        publication_start +
        key_match.end()
    )

    add_entity(
        entities,
        key_start,
        key_end,
        text[key_start:key_end],
        "PUB_KEY"
    )

    value_pattern = re.compile(
        r'\d+'
    )

    value_start = key_match.end()

    for value_match in value_pattern.finditer(
        publication_text,
        value_start
    ):

        start = (
            publication_start +
            value_match.start()
        )

        end = (
            publication_start +
            value_match.end()
        )

        add_entity(
            entities,
            start,
            end,
            text[start:end],
            "PUB_VAL"
        )

    return entities


def find_references(text):
    """Find all supported legal references and return sorted annotations."""

    entities = []

    for match in DU_PATTERN.finditer(text):

        entities.extend(
            process_du_mp_publication(
                text,
                match
            )
        )

    for match in MP_PATTERN.finditer(text):
    
        entities.extend(
            process_du_mp_publication(
                text,
                match
            )
        )

    for match in DUE_PATTERN.finditer(text):
    
        entities.extend(
            process_eu_publication(
                text,
                match
            )
        )

    for match in DWE_PATTERN.finditer(text):
    
        entities.extend(
            process_eu_publication(
                text,
                match
            )
        )


    # Process each reference family with its corresponding key and value pattern.
    # ART
    for match in ART_PATTERN.finditer(text):

        entities.extend(
            process_reference(
                text,
                match,
                "ART",
                re.compile(
                    r'\bart\.',
                    re.IGNORECASE
                ),
                re.compile(
                    r'\d+[a-z]*',
                    re.IGNORECASE
                )
            )
        )

    # PAR
    for match in PAR_PATTERN.finditer(text):

        entities.extend(
            process_reference(
                text,
                match,
                "PAR",
                re.compile(r'§'),
                re.compile(
                    r'\d+[a-z]*',
                    re.IGNORECASE
                )
            )
        )

    # UST
    for match in UST_PATTERN.finditer(text):

        entities.extend(
            process_reference(
                text,
                match,
                "UST",
                re.compile(
                    r'\bust\.',
                    re.IGNORECASE
                ),
                re.compile(
                    r'\d+[a-z]*',
                    re.IGNORECASE
                )
            )
        )

    # PKT
    for match in PKT_PATTERN.finditer(text):

        entities.extend(
            process_reference(
                text,
                match,
                "PKT",
                re.compile(
                    r'\bpkt\.?',
                    re.IGNORECASE
                ),
                re.compile(
                    r'\d+[a-z]*',
                    re.IGNORECASE
                )
            )
        )

    # LIT
    for match in LIT_PATTERN.finditer(text):

        entities.extend(
            process_reference(
                text,
                match,
                "LIT",
                re.compile(
                    r'\blit\.',
                    re.IGNORECASE
                ),
                re.compile(
                    r'[a-z]+',
                    re.IGNORECASE
                )
            )
        )

    # TIRET
    for match in TIR_PATTERN.finditer(text):

        entities.extend(
            process_reference(
                text,
                match,
                "TIR",
                re.compile(
                    r'\btiret',
                    re.IGNORECASE
                ),
                re.compile(
                    rf'(?:{ORDINALS})',
                    re.IGNORECASE
                )
            )
        )

    # PODWÓJNY TIRET
    for match in PODW_TIR_PATTERN.finditer(text):

        entities.extend(
            process_reference(
                text,
                match,
                "PODW_TIR",
                re.compile(
                    r'\bpodwójne\s+tiret',
                    re.IGNORECASE
                ),
                re.compile(
                    rf'(?:{ORDINALS})',
                    re.IGNORECASE
                )
            )
        )

    # ZDANIE
    for match in ZDA_PATTERN.finditer(text):

        entities.extend(
            process_reference(
                text,
                match,
                "ZDA",
                re.compile(
                    r'\b(?:zdanie|zdania|zdaniu|zdaniem)',
                    re.IGNORECASE
                ),
                re.compile(
                    rf'(?:{ORDINALS})',
                    re.IGNORECASE
                )
            )
        )

    entities.sort(
        key=lambda x: (
            x["value"]["start"],
            x["value"]["end"]
        )
    )

    return entities


def save_to_json(text, entities, output_path):
    """Write source text and annotations in the expected JSON format."""

    data = {
        "data": {
            "text": text
        },
        "predictions": [
            {
                "model_version": "regex-1.0",
                "result": entities
            }
        ]
    }

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def main():
    """Annotate every processed TXT file and save one JSON file per document."""
    input_dir = Path("data/processed/txt")
    output_dir = Path("data/processed/json")

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    files = list(
        input_dir.glob("*.txt")
    )

    if not files:
        print("Nie znaleziono plików TXT.")
        return

    for file_path in files:

        print(
            f"\nPrzetwarzanie: {file_path.name}"
        )

        text = file_path.read_text(
            encoding="utf-8"
        )

        entities = find_references(text)

        output_path = (
            output_dir /
            f"{file_path.stem}.json"
        )

        save_to_json(
            text,
            entities,
            output_path
        )

        print(
            f"  znaleziono: {len(entities)} encji"
        )

        print(
            f"  zapisano: {output_path}"
        )

if __name__ == "__main__":
    main()