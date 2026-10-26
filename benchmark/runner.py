import os
import sys
import time
import uuid
import json
import csv
import argparse
import httpx
import statistics
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try importing boto3 safely for queue backlog observation
try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

class CloudDocBenchmark:
    def __init__(
        self,
        base_url: str,
        sqs_queue_name: Optional[str] = "clouddoc-document-processing",
        aws_region: Optional[str] = "us-east-1",
        poll_interval: float = 1.0,
        poll_timeout: float = 60.0,
        cleanup: bool = False
    ):
        self.base_url = base_url.rstrip("/")
        self.sqs_queue_name = sqs_queue_name
        self.aws_region = aws_region
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.cleanup = cleanup
        
        self.token: Optional[str] = None
        self.user_email: Optional[str] = None
        self.sqs_client = None
        self.sqs_queue_url = None
        
        if HAS_BOTO3 and sqs_queue_name:
            try:
                self.sqs_client = boto3.client("sqs", region_name=aws_region)
                resp = self.sqs_client.get_queue_url(QueueName=sqs_queue_name)
                self.sqs_queue_url = resp.get("QueueUrl")
            except Exception as e:
                # AWS credentials or SQS queue not available from current context
                self.sqs_client = None
                self.sqs_queue_url = None

    def authenticate(self) -> bool:
        """Create a dedicated, unique benchmark test user and retrieve JWT token."""
        unique_suffix = uuid.uuid4().hex[:8]
        self.user_email = f"benchmark_runner_{unique_suffix}@benchmark.internal"
        password = f"BenchPass!{uuid.uuid4().hex[:12]}"

        # 1. Register
        reg_payload = {"email": self.user_email, "password": password}
        try:
            reg_resp = httpx.post(
                f"{self.base_url}/auth/register",
                json=reg_payload,
                timeout=10.0
            )
            if reg_resp.status_code not in (201, 409):
                print(f"[AUTH ERROR] Register failed with status {reg_resp.status_code}: {reg_resp.text}")
                return False

            # 2. Login
            login_resp = httpx.post(
                f"{self.base_url}/auth/login",
                json=reg_payload,
                timeout=10.0
            )
            if login_resp.status_code == 200:
                self.token = login_resp.json().get("access_token")
                print(f"[AUTH] Successfully authenticated benchmark session for user {self.user_email}")
                return True
            else:
                print(f"[AUTH ERROR] Login failed with status {login_resp.status_code}: {login_resp.text}")
                return False
        except Exception as e:
            print(f"[AUTH EXCEPTION] Failed to connect to auth endpoint: {e}")
            return False

    def get_queue_backlog(self) -> Optional[Dict[str, int]]:
        """Safely fetch SQS approximate message counts if available."""
        if not self.sqs_client or not self.sqs_queue_url:
            return None
        try:
            attrs = self.sqs_client.get_queue_attributes(
                QueueUrl=self.sqs_queue_url,
                AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
            ).get("Attributes", {})
            return {
                "available": int(attrs.get("ApproximateNumberOfMessages", 0)),
                "in_flight": int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
            }
        except Exception:
            return None

    def process_single_document_async(
        self,
        pdf_path: str,
        operation_index: int
    ) -> Dict[str, Any]:
        """
        Executes one full asynchronous document upload and poll cycle.
        Tracks upload API latency, direct S3 upload time, worker turnaround, and e2e processing time.
        """
        result = {
            "operation_index": operation_index,
            "filename": os.path.basename(pdf_path),
            "file_size_bytes": os.path.getsize(pdf_path),
            "upload_initiation_ms": None,
            "s3_upload_ms": None,
            "worker_turnaround_ms": None,
            "e2e_processing_ms": None,
            "document_id": None,
            "status": "INIT",
            "error_category": None,
            "poll_attempts": 0
        }

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        headers = {"Authorization": f"Bearer {self.token}"}
        bench_filename = f"bench_{uuid.uuid4().hex[:8]}_{os.path.basename(pdf_path)}"

        overall_start = time.perf_counter()

        # Step 1: Upload-initiation API call
        t_init_start = time.perf_counter()
        try:
            init_resp = httpx.post(
                f"{self.base_url}/documents/upload-url",
                json={"filename": bench_filename, "content_type": "application/pdf"},
                headers=headers,
                timeout=10.0
            )
            t_init_end = time.perf_counter()
            result["upload_initiation_ms"] = round((t_init_end - t_init_start) * 1000, 2)

            if init_resp.status_code != 201:
                result["status"] = "FAILED"
                result["error_category"] = f"INIT_HTTP_{init_resp.status_code}"
                return result

            init_data = init_resp.json()
            doc_id = init_data.get("document_id")
            upload_url = init_data.get("upload_url")
            result["document_id"] = doc_id

            if not upload_url:
                result["status"] = "FAILED"
                result["error_category"] = "MISSING_PRESIGNED_URL"
                return result

        except Exception as e:
            result["status"] = "FAILED"
            result["error_category"] = f"INIT_EXCEPTION_{type(e).__name__}"
            return result

        # Step 2: Direct S3 Upload via presigned PUT URL
        t_s3_start = time.perf_counter()
        try:
            s3_resp = httpx.put(
                upload_url,
                content=pdf_bytes,
                headers={"Content-Type": "application/pdf"},
                timeout=30.0
            )
            t_s3_end = time.perf_counter()
            result["s3_upload_ms"] = round((t_s3_end - t_s3_start) * 1000, 2)

            if s3_resp.status_code not in (200, 204):
                result["status"] = "FAILED"
                result["error_category"] = f"S3_HTTP_{s3_resp.status_code}"
                return result
        except Exception as e:
            result["status"] = "FAILED"
            result["error_category"] = f"S3_EXCEPTION_{type(e).__name__}"
            return result

        # Step 3: Polling for worker processing completion
        t_s3_finish = time.perf_counter()
        poll_start = time.perf_counter()
        while (time.perf_counter() - poll_start) < self.poll_timeout:
            result["poll_attempts"] += 1
            try:
                doc_resp = httpx.get(
                    f"{self.base_url}/documents/{doc_id}",
                    headers=headers,
                    timeout=10.0
                )
                if doc_resp.status_code == 200:
                    doc_data = doc_resp.json()
                    doc_status = doc_data.get("status")

                    if doc_status == "completed":
                        overall_end = time.perf_counter()
                        result["status"] = "COMPLETED"
                        result["e2e_processing_ms"] = round((overall_end - overall_start) * 1000, 2)
                        result["worker_turnaround_ms"] = round((overall_end - t_s3_finish) * 1000, 2)
                        break
                    elif doc_status == "failed":
                        overall_end = time.perf_counter()
                        result["status"] = "FAILED"
                        result["error_category"] = "WORKER_EXTRACTION_FAILED"
                        result["e2e_processing_ms"] = round((overall_end - overall_start) * 1000, 2)
                        break
            except Exception:
                pass

            time.sleep(self.poll_interval)

        if result["status"] not in ("COMPLETED", "FAILED"):
            result["status"] = "TIMEOUT"
            result["error_category"] = "POLL_TIMEOUT"
            result["e2e_processing_ms"] = round((time.perf_counter() - overall_start) * 1000, 2)

        # Optional Cleanup
        if self.cleanup and doc_id:
            try:
                httpx.delete(f"{self.base_url}/documents/{doc_id}", headers=headers, timeout=5.0)
            except Exception:
                pass

        return result

    def run_workload(
        self,
        pdf_path: str,
        total_documents: int,
        concurrency: int,
        workload_label: str
    ) -> Dict[str, Any]:
        """Run a batch workload with specified concurrency and compute full benchmark statistics."""
        print(f"\n=======================================================")
        print(f"Starting Test: {workload_label}")
        print(f"File: {os.path.basename(pdf_path)} ({os.path.getsize(pdf_path)} bytes)")
        print(f"Total Documents: {total_documents} | Concurrency: {concurrency}")
        print(f"Target URL: {self.base_url}")
        
        backlog_before = self.get_queue_backlog()
        if backlog_before:
            print(f"Initial SQS Backlog: {backlog_before['available']} available, {backlog_before['in_flight']} in-flight")
        print(f"=======================================================")

        batch_start = time.perf_counter()
        records: List[Dict[str, Any]] = []

        if concurrency == 1:
            for i in range(total_documents):
                rec = self.process_single_document_async(pdf_path, i + 1)
                records.append(rec)
                print(f"  [Doc {i+1}/{total_documents}] Status: {rec['status']} | "
                      f"API Latency: {rec['upload_initiation_ms']} ms | "
                      f"S3 PUT: {rec['s3_upload_ms']} ms | "
                      f"E2E: {rec['e2e_processing_ms']} ms")
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {
                    executor.submit(self.process_single_document_async, pdf_path, i + 1): i + 1
                    for i in range(total_documents)
                }
                for fut in as_completed(futures):
                    rec = fut.result()
                    records.append(rec)
                    print(f"  [Doc {rec['operation_index']}/{total_documents}] Status: {rec['status']} | "
                          f"API Latency: {rec['upload_initiation_ms']} ms | "
                          f"S3 PUT: {rec['s3_upload_ms']} ms | "
                          f"E2E: {rec['e2e_processing_ms']} ms")

        batch_end = time.perf_counter()
        total_wall_clock_sec = batch_end - batch_start

        backlog_after = self.get_queue_backlog()
        if backlog_after:
            print(f"Final SQS Backlog: {backlog_after['available']} available, {backlog_after['in_flight']} in-flight")

        # Compute summary statistics
        completed_records = [r for r in records if r["status"] == "COMPLETED"]
        successful_count = len(completed_records)
        failed_count = len(records) - successful_count
        success_rate = (successful_count / len(records)) * 100 if records else 0.0

        throughput_dpm = (successful_count / total_wall_clock_sec) * 60.0 if total_wall_clock_sec > 0 else 0.0

        def calc_percentiles(values: List[float]):
            if not values:
                return {"p50": None, "p95": None, "p99": None}
            s = sorted(values)
            n = len(s)
            p50 = statistics.median(s)
            p95 = s[min(int(0.95 * n), n - 1)]
            p99 = s[min(int(0.99 * n), n - 1)] if n >= 20 else None
            return {
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2) if p99 is not None else "N/A (<20 samples)"
            }

        api_latencies = [r["upload_initiation_ms"] for r in records if r["upload_initiation_ms"] is not None]
        s3_durations = [r["s3_upload_ms"] for r in records if r["s3_upload_ms"] is not None]
        e2e_durations = [r["e2e_processing_ms"] for r in completed_records if r["e2e_processing_ms"] is not None]
        worker_durations = [r["worker_turnaround_ms"] for r in completed_records if r["worker_turnaround_ms"] is not None]

        summary = {
            "workload_label": workload_label,
            "file": os.path.basename(pdf_path),
            "file_size_bytes": os.path.getsize(pdf_path),
            "total_attempted": len(records),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "success_rate_pct": round(success_rate, 2),
            "wall_clock_sec": round(total_wall_clock_sec, 2),
            "throughput_docs_per_min": round(throughput_dpm, 2),
            "upload_initiation_api_stats": calc_percentiles(api_latencies),
            "direct_s3_upload_stats": calc_percentiles(s3_durations),
            "end_to_end_stats": calc_percentiles(e2e_durations),
            "worker_turnaround_stats": calc_percentiles(worker_durations),
            "backlog_before": backlog_before,
            "backlog_after": backlog_after,
            "records": records
        }

        return summary


def save_results(all_summaries: List[Dict[str, Any]], output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = int(time.time())

    # 1. Save detailed JSON
    json_path = os.path.join(output_dir, f"benchmark_summary_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump(all_summaries, f, indent=2)
    print(f"\n[OUTPUT] Saved detailed JSON report to: {json_path}")

    # 2. Save raw individual operations to CSV
    csv_path = os.path.join(output_dir, f"raw_operations_{timestamp}.csv")
    with open(csv_path, "w", newline="") as f:
        fieldnames = [
            "workload_label", "operation_index", "filename", "file_size_bytes",
            "status", "upload_initiation_ms", "s3_upload_ms", "worker_turnaround_ms",
            "e2e_processing_ms", "poll_attempts", "error_category"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for summary in all_summaries:
            label = summary["workload_label"]
            for r in summary["records"]:
                row = {
                    "workload_label": label,
                    "operation_index": r["operation_index"],
                    "filename": r["filename"],
                    "file_size_bytes": r["file_size_bytes"],
                    "status": r["status"],
                    "upload_initiation_ms": r["upload_initiation_ms"],
                    "s3_upload_ms": r["s3_upload_ms"],
                    "worker_turnaround_ms": r["worker_turnaround_ms"],
                    "e2e_processing_ms": r["e2e_processing_ms"],
                    "poll_attempts": r["poll_attempts"],
                    "error_category": r["error_category"]
                }
                writer.writerow(row)
    print(f"[OUTPUT] Saved raw operations CSV to: {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CloudDoc Benchmark Runner")
    parser.add_argument("--url", default="http://35.170.58.177", help="Base URL of CloudDoc service")
    parser.add_argument("--mode", choices=["smoke", "full", "sync-comparison"], default="smoke", help="Benchmark run mode")
    parser.add_argument("--cleanup", action="store_true", help="Delete benchmark documents after testing")
    args = parser.parse_args()

    bench = CloudDocBenchmark(base_url=args.url, cleanup=args.cleanup)
    if not bench.authenticate():
        print("[ERROR] Authentication failed. Aborting benchmark.")
        sys.exit(1)

    workload_dir = os.path.join(os.path.dirname(__file__), "workload")
    small_pdf = os.path.join(workload_dir, "small_1p.pdf")
    medium_pdf = os.path.join(workload_dir, "medium_5p.pdf")
    large_pdf = os.path.join(workload_dir, "large_20p.pdf")

    results = []

    if args.mode == "smoke":
        # Smallest safe smoke test: exactly 1 document
        res = bench.run_workload(
            pdf_path=small_pdf,
            total_documents=1,
            concurrency=1,
            workload_label="Smoke Test (1 document, sequential)"
        )
        results.append(res)

    elif args.mode == "full":
        # 1. Warm-up & 1 document sequential
        res1 = bench.run_workload(
            pdf_path=small_pdf,
            total_documents=1,
            concurrency=1,
            workload_label="Scenario 1: Single Document Baseline (1 doc, concurrency=1)"
        )
        results.append(res1)

        # 2. Batch of 5 documents (Concurrency 2)
        res2 = bench.run_workload(
            pdf_path=medium_pdf,
            total_documents=5,
            concurrency=2,
            workload_label="Scenario 2: Controlled Batch (5 docs, concurrency=2)"
        )
        results.append(res2)

        # 3. Batch of 10 documents (Concurrency 5)
        res3 = bench.run_workload(
            pdf_path=large_pdf,
            total_documents=10,
            concurrency=5,
            workload_label="Scenario 3: Scaled Controlled Batch (10 docs, concurrency=5)"
        )
        results.append(res3)

    out_dir = os.path.join(os.path.dirname(__file__), "results")
    save_results(results, out_dir)
