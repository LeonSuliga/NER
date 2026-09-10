import requests
import random 
import time
import csv
from pathlib import Path 

API_URL = "https://api.sejm.gov.pl/eli/acts/search"

# Keep downloaded source files separate from processed datasets.
OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR_PDF = OUTPUT_DIR / "PDF"
OUTPUT_DIR_PDF.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR_HTML = OUTPUT_DIR / "HTML"
OUTPUT_DIR_HTML.mkdir(parents=True, exist_ok=True)

metadata_file = OUTPUT_DIR / "metadata.csv"

YEAR = 2024

types = [
    'Rozporządzenie',
    'Obwieszczenie',
    'Ustawa'
]

number_of_documents_per_type = [
    20,  # Rozporządzenie
    20,  # Obwieszczenie
    10   # Ustawa
]   

def get_random_acts(year, type, number_of_documents=5):
    """Download a deterministic random sample of acts for one document type."""
    params = {
        "publisher": "DU",
        "year": YEAR,
        "type": type,
        "textHTML": True
    }

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    acts = data["items"]

    print(f"Selected acts: {len(acts)}, type: {type}, year: {year}")

    random.seed(42)

    random_acts = random.sample(
        acts, 
        number_of_documents)

    print(f"Random acts: {len(random_acts)}")

    for i, act in enumerate(random_acts, start=1):
        position = act["pos"]

        pdf_url = (
            f"https://api.sejm.gov.pl/"
            f"eli/acts/DU/{year}/{position}/text.pdf"
        )

        html_url = (
            f"https://api.sejm.gov.pl/"
            f"eli/acts/DU/{year}/{position}/text.html"
        )

        filename_pdf = OUTPUT_DIR_PDF / f"DU_{year}_{position}.pdf"
        filename_html = OUTPUT_DIR_HTML / f"DU_{year}_{position}.html"

        # Download the PDF version first; a failure here should not stop the batch.
        try: 
            pdf_response = requests.get(pdf_url, timeout=60)
            pdf_response.raise_for_status()

            filename_pdf.write_bytes(pdf_response.content)

            print(
                f"[{i}/{len(random_acts)}] Downloaded Dz.U. {year} poz. {position} to: {filename_pdf}"
            )

        except requests.RequestException as e:
            print(
                f"[{i}/{len(random_acts)}] Error downloading Dz.U. {year} poz. {position}: {e}"
            )

        time.sleep(0.5)

        # The HTML version is used for text extraction and is also recorded in metadata.
        try: 
            html_response = requests.get(html_url, timeout=60)
            html_response.raise_for_status()
    
            filename_html.write_bytes(html_response.content)
    
            print(
                f"[{i}/{len(random_acts)}] Downloaded Dz.U. {year} poz. {position} to: {filename_html}"
            )

            file_exists = metadata_file.exists()

            with open(metadata_file, "a", newline="", encoding="utf-8") as f:
            
                fieldnames = [
                    "position",
                    "title",
                    "type",
                    "publication_date",
                    "eli"
                ]
        
                writer = csv.DictWriter(
                    f,
                    fieldnames=fieldnames
                )
        
                if not file_exists:
                    writer.writeheader()
        
                writer.writerow({
                    "position": act["pos"],
                    "title": act["title"],
                    "type": act["type"],
                    "publication_date": act.get("promulgation"),
                    "eli": act["ELI"]
                })
        
        except requests.RequestException as e:
            print(
                f"[{i}/{len(random_acts)}] Error downloading Dz.U. {year} poz. {position}: {e}"
            )

        time.sleep(0.5)
         
for type, number_of_documents in zip(types, number_of_documents_per_type):
    get_random_acts(
        year=YEAR,
        type=type,
        number_of_documents=number_of_documents
    )


