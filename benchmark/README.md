# CloudDoc Performance Benchmark Suite

This directory contains a reproducible performance benchmarking suite for evaluating CloudDoc's asynchronous PDF-processing architecture against a synchronous baseline.

## 📁 Directory Structure

```
benchmark/
├── workload/                      # Controlled, synthetic PDF test workloads
│   ├── small_1p.pdf               # 1 page (~1.5 KB)
│   ├── medium_5p.pdf              # 5 pages (~5.5 KB)
│   └── large_20p.pdf              # 20 pages (~20.5 KB)
├── results/                       # Raw per-operation benchmark data (JSON & CSV)
├── generate_workload.py           # Workload generator using PyMuPDF
├── sync_baseline.py               # Synchronous baseline implementation using identical extraction
├── compare_sync_async.py          # Comparative analysis runner
├── runner.py                      # Multi-scenario asynchronous benchmark runner
├── BENCHMARK_REPORT.md            # In-depth benchmark analysis report
└── README.md                      # Setup and execution guide
```

---

## 🛠️ Prerequisites

1. **Python 3.11+** with virtual environment active:
   ```bash
   .\backend\venv\Scripts\activate
   ```
2. **Dependencies**: `httpx`, `pymupdf` (fitz), `sqlalchemy`, `boto3`, `pydantic-settings`.
3. **Target Environment**:
   - Deployed EC2 CloudDoc instance (e.g., `http://35.170.58.177`) or local FastAPI instance.
   - Optional AWS credentials with read permissions on the target SQS queue for backlog telemetry.

---

## 🚀 Running the Benchmarks

### 1. Generate Synthetic PDF Workload
```bash
python benchmark/generate_workload.py
```

### 2. Run Synchronous Baseline
Evaluates synchronous PDF extraction and database persistence latency:
```bash
$env:DATABASE_URL="postgresql+psycopg://postgres:prashant@localhost:5432/clouddoc"
python benchmark/compare_sync_async.py
```

### 3. Run Asynchronous Smoke Test (1 Document)
```bash
python benchmark/runner.py --mode smoke --url http://35.170.58.177
```

### 4. Run Full Multi-Scenario Asynchronous Benchmark
Executes 1-doc sequential baseline, 5-doc batch (concurrency 2), and 10-doc batch (concurrency 5):
```bash
python benchmark/runner.py --mode full --url http://35.170.58.177 --cleanup
```

---

## 🔒 Safety & Cost Control Guardrails

- **Zero Secret Exposure**: Tokens, passwords, and presigned URLs are never logged or exported in reports.
- **Dedicated Test Identities**: Benchmark creates isolated test accounts (`benchmark_runner_<uuid>@benchmark.internal`) and prefixes document keys.
- **Non-Aggressive Concurrency**: Strictly capped at low batch volumes (1, 5, 10 docs) to prevent EC2 `t3.micro` saturation or AWS throttling.
- **Automated Cleanup**: The `--cleanup` flag automatically issues `DELETE` requests for benchmark-created records.
- **Monotonic Clocks**: All timings use Python's `time.perf_counter()` to eliminate wall-clock drift.
