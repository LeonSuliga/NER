import json
from pathlib import Path


def transform_exact_format_for_label_studio(file_input):
    """
    Przekształca plik JSON o strukturze zagnieżdżonej (z obiektem 'task' i 'result' na zewnątrz)
    do formatu bezpośrednio akceptowanego przez mechanizm importu Label Studio.
    """
    # Główna ścieżka do pliku w folderze data/labeled/part3/
    base_dir = Path("data/labeled/part3")
    path = base_dir / str(file_input)

    # Obsługa pliku bez rozszerzenia lub z rozszerzeniem w docelowym folderze
    if not path.exists():
        # Sprawdzamy czy istnieje wersja z rozszerzeniem .json w tym samym folderze
        json_path = base_dir / f"{file_input}.json"
        if json_path.exists():
            path = json_path
        else:
            # Jeśli plik fizycznie nie istnieje, pomijamy tę iterację (zgodnie z intencją pętli for)
            return

    with open(path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    # Upewniamy się, że pracujemy na liście obiektów
    if isinstance(raw_data, dict):
        items = [raw_data]
    elif isinstance(raw_data, list):
        items = raw_data
    else:
        raise ValueError("Nieobsługiwany format JSON. Oczekiwano słownika lub listy.")

    transformed_tasks = []

    for item in items:
        task = {}

        # 1. Wyciąganie sekcji 'data' z obiektu 'task', jeśli istnieje w strukturze
        if 'task' in item and isinstance(item['task'], dict):
            task_inner = item['task']
            if 'data' in task_inner:
                task['data'] = task_inner['data']
            else:
                # Awaryjnie, gdyby w 'task' nie było klucza 'data'
                task['data'] = {"text": "[Brak tekstu w zadaniu]"}

            # Opcjonalnie: zachowanie ID zadania z wnętrza 'task' jeśli jest potrzebne
            if 'id' in task_inner:
                task['id'] = task_inner['id']
        elif 'data' in item:
            # Gdyby dane były bezpośrednio w głównym słowniku
            task['data'] = item['data']
        else:
            raise ValueError("Brak struktury 'data' lub 'task' w pliku wejściowym!")

        # 2. Przekształcenie 'result' na poprawną strukturę 'annotations'
        if 'result' in item and isinstance(item['result'], list):
            task['annotations'] = [
                {
                    "result": item['result']
                }
            ]
        elif 'annotations' in item:
            task['annotations'] = item['annotations']

        # 3. Zachowanie globalnego ID, jeśli istniało na najwyższym poziomie i nie zostało jeszcze przypisane
        if 'id' in item and 'id' not in task:
            task['id'] = item['id']

        transformed_tasks.append(task)

    # Przygotowanie folderu docelowego dla przetworzonych plików
    output_dir = base_dir / "to_check"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generowanie nazwy pliku wyjściowego
    output_path = output_dir / f"{path.stem}_to_check.json"

    # Zapis przekształconych danych
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(transformed_tasks, f, ensure_ascii=False, indent=2)

    print(f"Sukces! Przetworzono zadanie z pliku '{path.name}'. Zapisano jako: {output_path.name}")


if __name__ == "__main__":
    for i in range(1, 50):
        name = str(i)
        transform_exact_format_for_label_studio(name)