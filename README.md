# Polish Legal Citation NER

Trains and compares NER models for legal citations in Polish legal acts, using hand-labeled Label Studio annotations.

## Project structure

```text
.
├── data/
│   ├── raw/                  # Legal act HTML downloaded from the Sejm API (source documents)
│   ├── processed/            # Cleaned plain-text versions of the raw documents
│   ├── labeled/              # Hand-labeled Label Studio exports (the training data)
│   ├── ner_dataset.json      # Labels converted to project span format
│   ├── train_bio.json        # Labels converted to token-level BIO tags
│   └── spacy/                # train/dev/test DocBins shared by all models
├── annotation_cleaning/      # Check and fix the hand-labeled files
│   ├── audit_annotations.py      # Report label stats and annotation problems
│   ├── deduplicate_spans.py      # Remove duplicate spans
│   ├── find_exact_overlaps.py    # List overlapping spans
│   └── clean_bad_lit_vals.py     # Remove overlapping LIT_VAL spans in files 5, 6, 38
├── data_prep/                # Labeled files -> training data
│   ├── labelstudio_to_project.py # data/labeled/   -> data/ner_dataset.json
│   ├── convert_dataset.py        # ner_dataset.json -> train_bio.json
│   └── convert_to_spacy.py       # train_bio.json  -> data/spacy/{train,dev,test}.spacy
├── training/                 # Train the three NER models
│   ├── train_spacy_ner.py        # Blank spaCy model         -> models/ner_spacy
│   ├── train_spacy_vectors.py    # spaCy + pl_core_news_md   -> models/ner_spacy_vectors
│   ├── train_herbert_ner.py      # HerBERT transformer       -> models/ner_herbert
│   └── configs/ner_spacy_vectors.cfg
├── evaluation/
│   ├── evaluate_model.py         # Score the blank spaCy model on the test set
│   └── compare_models.py         # Score all three models -> models/comparison.json
├── models/                   # Trained models and comparison results
├── archive/                  # Old ETL / Postgres / Neo4j / regex code, not used by this pipeline
├── run_pipeline.bat          # Runs data_prep -> training -> evaluation end to end
└── requirements.txt
```

## Usage

```bash
python -m pip install -r requirements.txt
python -m spacy download pl_core_news_md

# optional: check / clean the labeled files
python annotation_cleaning/audit_annotations.py --root . --only-labeled

# full pipeline (Windows)
run_pipeline.bat
```

Or step by step:

```bash
python data_prep/labelstudio_to_project.py
python data_prep/convert_dataset.py
python data_prep/convert_to_spacy.py
python training/train_spacy_ner.py
python training/train_spacy_vectors.py
python training/train_herbert_ner.py --epochs 3
python evaluation/compare_models.py
```

All scripts resolve paths from the project root, so they can be run from any directory.
