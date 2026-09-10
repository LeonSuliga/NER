import re
from pathlib import Path
from bs4 import BeautifulSoup

def clean_text(text):
    """Normalize whitespace and punctuation while preserving document lines."""
    text = text.replace("\xa0", " ")
    text = text.replace("\u2009", " ")
    text = text.replace("\u202f", " ")
    text = text.replace("\u2007", " ")

    text = text.replace("\t", " ")

    text = re.sub(r" {2,}", " ", text)

    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)

    text = re.sub(r"\s+([,.;:])", r"\1", text)

    text = re.sub(r"„\s+", "„", text)
    text = re.sub(r"\s+”", "”", text)

    lines = []

    for line in text.splitlines():

        line = line.strip()

        if line:
            lines.append(line)

    text = "\n".join(lines)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_document_body(soup):
    """Remove non-content elements and return the cleaned text from the body."""
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    for element in soup.select(".gloss-section"):
        element.decompose()

    show_all = soup.select_one("#show-all")

    if show_all:
        show_all.decompose()

    body = soup.find("body")

    if not body:
        return ""

    block_selectors = [
        "h1",
        "h2",
        "h3",
        ".unit",
        ".pro-text",
        ".cite-box",
    ]

    # Add line breaks around logical blocks before extracting all visible text.
    for selector in block_selectors:

        for element in soup.select(selector):

            element.insert_before(
                soup.new_string("\n")
            )

            element.insert_after(
                soup.new_string("\n")
            )

    text = body.get_text(
        " ",
        strip=False
    )

    text = clean_text(text)

    return text

def process_file(input_file, output_file):
    """Read one HTML file, extract its text, and write a TXT file."""

    print(f"Przetwarzanie: {input_file}")

    with open(
        input_file,
        "r",
        encoding="utf-8"
    ) as f:

        html = f.read()

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = extract_document_body(soup)

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(text)

    print(f"OK -> {output_file}")


def process_directory(input_dir, output_dir):
    """Process every HTML file in a directory."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    html_files = sorted(
        input_dir.glob("*.html")
    )

    print(
        f"Znaleziono {len(html_files)} plików HTML."
    )

    for html_file in html_files:

        output_file = (
            output_dir /
            f"{html_file.stem}.txt"
        )

        try:

            process_file(
                html_file,
                output_file
            )

        except Exception as e:

            print(
                f"BŁĄD podczas przetwarzania "
                f"{html_file.name}: {e}"
            )


if __name__ == "__main__":

    INPUT_DIR = "data/raw/HTML"
    OUTPUT_DIR = "data/processed/txt"

    process_directory(
        INPUT_DIR,
        OUTPUT_DIR
    )