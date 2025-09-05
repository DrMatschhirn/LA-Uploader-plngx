from pathlib import Path

def upload(file: Path, work_dir: Path, meta: dict) -> dict:
    # TODO: Später mit Playwright implementieren
    # Hier nur Dummy-Implementierung
    # z. B. Datei kopieren, um die Struktur zu sehen
    copied = work_dir / file.name
    if not copied.exists():
        copied.write_bytes(file.read_bytes())
    # Gib strukturierte Infos zurück
    return {
        "target": "debeka",
        "uploaded_file": str(file),
        "note": "Dummy-Upload. Implement Playwright flow."
    }
