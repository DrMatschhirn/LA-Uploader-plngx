from pathlib import Path

def upload(file: Path, work_dir: Path, meta: dict) -> dict:
    copied = work_dir / file.name
    if not copied.exists():
        copied.write_bytes(file.read_bytes())
    return {
        "target": "ebeihilfe",
        "uploaded_file": str(file),
        "note": "Dummy-Upload. Implement Playwright flow."
    }
