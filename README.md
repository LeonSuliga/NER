# Legal Citation Entity Linking Pipeline

This project builds a legal citation extraction and entity-linking pipeline for Polish legal acts. It combines:

- ETL for Sejm ELI metadata
- PostgreSQL with pgvector for deterministic, fuzzy, and semantic matching
- Neo4j for legal act graph relationships
- rule-based citation extraction and NER dataset tooling
- optional spaCy training for sequence labeling

The target use case is a legal reference resolver that can map a string like `Dz. U. z 2020 r. poz. 1` to the corresponding legal act ID and provide confidence and match method.

## System requirements

- Operating system: Linux / WSL2 (Ubuntu 22.04 LTS)
- Python: 3.11 or 3.12
- Docker: required for PostgreSQL + pgvector and Neo4j
- Optional: Windows native Python 3.14 + MinGW/MSYS2 is not supported for spaCy/thinc due to missing prebuilt wheels and native compilation issues

## Architecture

The project is organized in four layers:

1. ETL layer
   - Fetch legal act metadata from the Sejm ELI API
   - Normalize and stage records in JSONL
2. Relational + vector layer
   - PostgreSQL with pgvector
   - Structured legal act storage and embeddings
3. Graph layer
   - Neo4j legal act graph with amendment/repeal relations
4. Extraction and resolution layer
   - regex_ner.py for rule-based parsing
   - entity_linker.py for exact / fuzzy / vector matching
   - optional spaCy NER training pipeline

## Project structure

```text
.
├── etl_sejm.py                  # Fetch and normalize ELI metadata
├── load_pg.py                  # Load staging JSONL into PostgreSQL
├── schema.sql                  # PostgreSQL schema and indexes
├── build_graph.py              # Load acts and relations into Neo4j
├── entity_linker.py            # Exact / fuzzy / vector legal act resolver
├── regex_ner.py                # Rule-based legal citation parser
├── test_full_pipeline.py       # Full regex -> linker end-to-end check
├── generate_ner_dataset.py     # Generate synthetic legal NER examples
├── convert_dataset.py          # Convert spans to BIO labels
├── convert_to_spacy.py         # Convert BIO to spaCy DocBin
├── train_spacy_ner.py          # Train a spaCy NER model
├── evaluate_pipeline.py        # Compare regex and model outputs
├── constraints.cypher          # Neo4j uniqueness and index constraints
├── docker-compose.yml          # PostgreSQL + Neo4j runtime configuration
├── requirements.txt            # Python dependencies
├── data/                       # Generated NER data and conversion outputs
├── staging/                    # ETL JSONL output
├── models/                     # Trained spaCy models
├── scripts/                    # Validation and sample queries
├── README.md                   # Project documentation
└── .venv/                      # Local virtual environment
```

## Quickstart

### 1. Create a Python virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

If you are using WSL2, install the system packages first when needed:

```bash
sudo apt-get update
sudo apt-get install python3.11 python3.11-venv python3.11-dev
```

### 2. Start the required services with Docker

```bash
docker compose up -d postgres neo4j
```

This starts:

- PostgreSQL with pgvector on `localhost:5432`
- Neo4j on `localhost:7687` and the browser UI on `localhost:7474`

### 3. Run the ETL ingest

```bash
python etl_sejm.py --publisher dziennik_ustaw --year 2020 --out staging/du_2020_test.jsonl --insecure --per-page 20 --limit 10
```

This downloads detailed legal act records from the Sejm ELI API and writes JSONL staging entries.

### 4. Load data into PostgreSQL

```bash
python load_pg.py --db-url postgresql://postgres:postgres@localhost:5432/legaldb --staging-dir ./staging --embed-model fallback --vector-dim 768
```

This loads the legal acts, aliases, and optional vector embeddings into the PostgreSQL schema.

### 5. Load graph data into Neo4j

```bash
python build_graph.py --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-pass neo4jpass --staging-dir ./staging
```

This creates `:LegalAct` nodes and graph edges such as `:AMENDS` and `:REPEALS` when relation metadata is present in the staging records.

### 6. Generate synthetic NER data and convert it

```bash
python generate_ner_dataset.py
python convert_dataset.py
python convert_to_spacy.py
```

This generates the synthetic legal-citation dataset and converts it to spaCy DocBin format for training.

### 7. Train the spaCy model and evaluate

```bash
python train_spacy_ner.py --epochs 15
python evaluate_pipeline.py
```

The trained model is written to `models/ner_spacy`.

### 8. Run the full pipeline test

```bash
python test_full_pipeline.py
```

This performs a rule-based parse of raw legal citation strings, resolves them via `entity_linker.py`, and prints the matching act ID and processing time.

## Notes on dependencies and platform support

- This project expects Linux / WSL2 for reliable native builds of spaCy, thinc, and related NLP packages.
- Python 3.14 on Windows MinGW/MSYS2 is not the recommended runtime for training and evaluation because prebuilt wheels are missing or compilation fails.
- The code uses deterministic fallback embeddings when a sentence-transformers model is unavailable, which is useful for testing but not a substitute for a real semantic model.

## Typical workflow

```bash
# 1) Setup environment
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 2) Start infrastructure
docker compose up -d

# 3) Fetch ETL data
python etl_sejm.py --publisher dziennik_ustaw --year 2020 --out staging/du_2020_test.jsonl --insecure --per-page 20 --limit 10

# 4) Load PostgreSQL and Neo4j
python load_pg.py --db-url postgresql://postgres:postgres@localhost:5432/legaldb --staging-dir ./staging --embed-model fallback --vector-dim 768
python build_graph.py --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-pass neo4jpass --staging-dir ./staging

# 5) NER generation and evaluation
python generate_ner_dataset.py
python convert_dataset.py
python convert_to_spacy.py
python train_spacy_ner.py --epochs 15
python evaluate_pipeline.py
python test_full_pipeline.py
```

## Troubleshooting

- If `spaCy` fails to install, switch to WSL2 or Ubuntu and use Python 3.11/3.12.
- If PostgreSQL or Neo4j is not ready, wait for Docker health checks to pass before running the loaders.
- If the Sejm API returns sparse metadata, the ETL falls back to constructing detail URLs from the act address.
