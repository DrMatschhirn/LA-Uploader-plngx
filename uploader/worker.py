# uploader/worker.py
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Targets dynamisch importieren
from importlib import import_module

# ---------------------------
# Konfiguration aus ENV
# ---------------------------
JOB_DIR = Path(os.getenv("JOB_DIR", "/jobs")).resolve()
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "3.0"))  # Sekunden
WORK_INBOX = JOB_DIR / "inbox"
WORK_PROCESSING = JOB_DIR / "processing"
WORK_DONE = JOB_DIR / "done"
WORK_FAILED = JOB_DIR / "failed"

# ---------------------------
# Modelle
# ---------------------------
@dataclass
class Job:
    id: str
    target: str           # "debeka" | "ebeihilfe"
    file: Path            # Pfad zur PDF
    meta: dict            # beliebige Zusatzinfos
    created_at: str       # ISO-String
    attempts: int = 0

    @staticmethod
    def from_json(p: Path) -> "Job":
        data = json.loads(p.read_text(encoding="utf-8"))
        # Pflichtfelder prüfen
        for key in ("id", "target", "file", "created_at"):
            if key not in data:
                raise ValueError(f"Job fehlt Feld '{key}': {p}")
        job = Job(
            id=str(data["id"]),
            target=str(data["target"]).lower(),
            file=Path(data["file"]),
            meta=data.get("meta", {}),
            created_at=str(data["created_at"]),
            attempts=int(data.get("attempts", 0)),
        )
        return job

# ---------------------------
# Utils
# ---------------------------
def log(level: str, msg: str, **fields):
    base = {"level": level, "msg": msg, "ts": int(time.time())}
    base.update(fields)
    print(json.dumps(base, ensure_ascii=False), flush=True)

def ensure_dirs():
    for d in (WORK_INBOX, WORK_PROCESSING, WORK_DONE, WORK_FAILED):
        d.mkdir(parents=True, exist_ok=True)

def load_target_module(name: str):
    # Module unter uploader.targets.<name> erwarten
    return import_module(f"uploader.targets.{name}")

def move(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    # Falls Name kollidiert, hänge Suffix an
    counter = 1
    while dst.exists():
        dst = dst_dir / f"{src.stem}__{counter}{src.suffix}"
        counter += 1
    return src.rename(dst)

def atomic_claim(p: Path, to_dir: Path) -> Optional[Path]:
    """
    Überführt eine Job-JSON aus inbox nach processing.
    Gibt den neuen Pfad zurück, wenn erfolgreich.
    """
    try:
        return move(p, to_dir)
    except Exception as e:
        log("error", "Konnte Job nicht in processing verschieben", file=str(p), error=str(e))
        return None

# ---------------------------
# Upload-Ausführung mit Retry
# ---------------------------
class UploadError(Exception):
    pass

@retry(
    retry=retry_if_exception_type(UploadError),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
def run_upload(job: Job, work_dir: Path):
    """
    Lädt die Datei gemäß job.target hoch.
    Erwartet, dass das Zielmodul eine Funktion upload(file: Path, work_dir: Path, meta: dict) -> dict zurückgibt.
    """
    try:
        target_mod = load_target_module(job.target)
    except ModuleNotFoundError as e:
        raise UploadError(f"Unbekanntes target '{job.target}'") from e

    # Sanity Checks
    pdf = job.file
    if not pdf.exists():
        raise UploadError(f"Datei existiert nicht: {pdf}")
    if pdf.suffix.lower() != ".pdf":
        raise UploadError(f"Nur PDF unterstützt, erhalten: {pdf.suffix}")

    # Arbeitsverzeichnis für Artefakte der einzelnen Ausführung
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = target_mod.upload(pdf, work_dir, job.meta)
        return result or {}
    except Exception as e:
        raise UploadError(str(e)) from e

# ---------------------------
# Main Loop
# ---------------------------
_shutdown = False
def _handle_sigterm(signum, frame):
    global _shutdown
    _shutdown = True
    log("info", "Shutdown-Signal empfangen", signum=signum)

def process_one(job_json: Path):
    # 1) in processing verschieben (lock)
    claimed = atomic_claim(job_json, WORK_PROCESSING)
    if not claimed:
        return

    # 2) Job laden
    try:
        job = Job.from_json(claimed)
    except Exception as e:
        log("error", "Ungültiger Job", file=str(claimed), error=str(e))
        move(claimed, WORK_FAILED)
        return

    # 3) Arbeitsordner
    job_work_dir = JOB_DIR / "runs" / job.id
    job_work_dir.mkdir(parents=True, exist_ok=True)

    log("info", "Starte Upload", job_id=job.id, target=job.target, file=str(job.file))

    # 4) Upload mit Retry
    try:
        result = run_upload(job, job_work_dir)
        # Ergebnis/Quittung ablegen
        receipt_path = job_work_dir / "result.json"
        receipt_path.write_text(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2), encoding="utf-8")

        # 5) JSON nach done verschieben
        move(claimed, WORK_DONE)
        log("info", "Upload erfolgreich", job_id=job.id, receipt=str(receipt_path))
    except Exception as e:
        # Fehler persistieren
        err_path = job_work_dir / "error.txt"
        err_path.write_text(str(e), encoding="utf-8")
        move(claimed, WORK_FAILED)
        log("error", "Upload fehlgeschlagen", job_id=job.id, error=str(e))

def main():
    ensure_dirs()
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    log("info", "Worker gestartet", job_dir=str(JOB_DIR), poll_interval=POLL_INTERVAL)

    while not _shutdown:
        # Alle .json in inbox alphabetisch
        jobs = sorted(WORK_INBOX.glob("*.json"))
        if not jobs:
            time.sleep(POLL_INTERVAL)
            continue

        for job_json in jobs:
            if _shutdown:
                break
            process_one(job_json)

    log("info", "Worker beendet")

if __name__ == "__main__":
    main()
