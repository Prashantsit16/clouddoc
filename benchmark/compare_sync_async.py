import os
import sys
import time
import json
import csv
import statistics
from typing import List, Dict, Any

# Ensure backend and project root can be imported
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
backend_dir = os.path.join(project_root, "backend")
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal, Base, engine
from app.models.document import Document
from app.models.user import User
from benchmark.sync_baseline import process_document_synchronous

def run_synchronous_benchmark(
    pdf_paths: List[str],
    iterations_per_file: int = 5
) -> Dict[str, Any]:
    """
    Executes synchronous document processing directly against the database and PyMuPDF,
    measuring execution latency for small, medium, and large PDFs.
    """
    db = SessionLocal()
    # Ensure test user exists for synchronous benchmark
    test_email = "sync_benchmark_runner@benchmark.internal"
    user = db.query(User).filter(User.email == test_email).first()
    if not user:
        user = User(email=test_email, password_hash="dummy_hash_for_benchmarking")
        db.add(user)
        db.commit()
        db.refresh(user)

    results_by_file = {}
    raw_records = []

    for path in pdf_paths:
        filename = os.path.basename(path)
        file_size = os.path.getsize(path)
        with open(path, "rb") as f:
            pdf_bytes = f.read()

        durations_ms = []
        for i in range(iterations_per_file):
            t_start = time.perf_counter()
            doc = process_document_synchronous(
                file_bytes=pdf_bytes,
                filename=f"sync_{i}_{filename}",
                user_id=user.id,
                db=db
            )
            t_end = time.perf_counter()
            dur_ms = round((t_end - t_start) * 1000, 2)
            durations_ms.append(dur_ms)
            raw_records.append({
                "architecture": "synchronous",
                "filename": filename,
                "file_size_bytes": file_size,
                "iteration": i + 1,
                "latency_ms": dur_ms,
                "document_id": doc.id,
                "status": doc.status
            })

        results_by_file[filename] = {
            "file_size_bytes": file_size,
            "iterations": iterations_per_file,
            "min_ms": round(min(durations_ms), 2),
            "median_p50_ms": round(statistics.median(durations_ms), 2),
            "p95_ms": round(sorted(durations_ms)[min(int(0.95 * len(durations_ms)), len(durations_ms) - 1)], 2),
            "max_ms": round(max(durations_ms), 2)
        }

    # Clean up sync benchmark documents
    db.query(Document).filter(Document.user_id == user.id).delete()
    db.commit()
    db.close()

    return {
        "summary": results_by_file,
        "raw_records": raw_records
    }

if __name__ == "__main__":
    workload_dir = os.path.join(os.path.dirname(__file__), "workload")
    files = [
        os.path.join(workload_dir, "small_1p.pdf"),
        os.path.join(workload_dir, "medium_5p.pdf"),
        os.path.join(workload_dir, "large_20p.pdf")
    ]
    print("Running Synchronous Processing Baseline...")
    res = run_synchronous_benchmark(files, iterations_per_file=5)
    print(json.dumps(res["summary"], indent=2))
