# CloudDoc: Comprehensive System Architecture & Technical Interview Guide

> **Purpose:** This guide equips you with deep, interview-ready mastery of CloudDoc. It breaks down the entire system flow into simple, intuitive concepts, dives into PostgreSQL internals, explains why each library and AWS service was chosen, and provides crisp, authoritative answers to high-frequency engineering interview questions.

---

## 🎯 1. The 60-Second Elevator Pitch

When an interviewer asks: *"Tell me about CloudDoc and the engineering challenges behind it,"* here is your golden answer:

> *"CloudDoc is a cloud-native document processing platform designed to solve a classic scalability bottleneck: **handling compute-heavy PDF processing without blocking web application servers**. 
> 
> Instead of routing massive binary files through our backend API and running CPU-intensive parsing on web threads, I designed an **event-driven, decoupled architecture**. The frontend retrieves a cryptographically signed presigned URL from FastAPI and uploads directly to Amazon S3. S3 event notifications automatically publish to Amazon SQS, which a pool of detached background workers consumes using PyMuPDF to extract text and persist results into PostgreSQL.
> 
> I recently implemented a reproducible benchmark across varying document complexities. The results demonstrated that while total end-to-end processing takes ~3.7 seconds, our **upload-initiation API latency remains virtually constant ($O(1)$) at ~640 ms** regardless of document page count—achieving 100% reliability at 56 documents per minute on low-cost EC2 infrastructure without any queue accumulation or web server starvation."*

---

## 🌊 2. Complete End-to-End System Flow (Simple & Clear)

Imagine CloudDoc as an upscale restaurant:
- **The Waiter (FastAPI Backend):** Greets you, gives you a secure ticket to drop off your luggage, and goes right back to greeting the next guest.
- **The Storage Locker (Amazon S3):** Holds the heavy bags directly so the waiter never carries luggage.
- **The Order Bell (Amazon SQS):** Rings when a new bag arrives in the locker.
- **The Kitchen Staff (Detached Background Worker):** Pulls the ticket when ready, takes the bag, reads the documents inside, and logs the recipe in the central ledger.
- **The Ledger (PostgreSQL Database):** Stores all user accounts, metadata, and extracted text.

```
+---------------+                1. POST /documents/upload-url
|               | --------------------------------------------> +--------------------+
|               | <-------------------------------------------- |   FastAPI Backend  |
|               |         2. HTTP 201 {presigned_url, doc_id}   +--------------------+
|               |                                                         |
|               | 3. Direct HTTP PUT (Raw binary stream)                  | 2a. INSERT status='pending'
|               | -----------------------------+                          v
| React Client  |                              |                  +--------------------+
|               |                              v                  | PostgreSQL Database|
|               |                     +-----------------+         +--------------------+
|               |                     |    Amazon S3    |                   ^
|               |                     |  Bucket Storage |                   |
|               |                     +-----------------+                   |
|               |                              |                            |
|               | 6. Polling: GET /doc/{id}    | 4. s3:ObjectCreated:*      | 5c. UPDATE status='completed',
|               | --------------------+        v                            |     extracted_text=...
|               | <-----------------  |   +-----------------+               |
+---------------+   Status: completed |   |    Amazon SQS   |               |
                                      |   | Processing Queue|               |
                                      |   +-----------------+               |
                                      |            |                        |
                                      |            | 5. Long Poll (20s)     |
                                      |            v                        |
                                      |   +-----------------+               |
                                      +-- |  Python Worker  | --------------+
                                          |    (PyMuPDF)    | 5a. Download from S3
                                          +-----------------+ 5b. Parse PDF bytes
```

### Step-by-Step Breakdown:

1. **Upload Initiation (`POST /documents/upload-url`):**
   - Client sends: `{"filename": "contract.pdf", "content_type": "application/pdf"}`.
   - FastAPI verifies the JWT token, sanitizes the filename to prevent path traversal attacks, and generates an S3 object key: `users/{user_id}/documents/{uuid4}-{safe_filename}`.
   - Backend calls Boto3 to generate a **presigned PUT URL** (valid for 10 minutes) and inserts a record into PostgreSQL with `status="pending"`.
   - Backend immediately responds with `upload_url` and `document_id`. (Elapsed: ~15–25 ms server execution).

2. **Direct-to-S3 Upload (Zero Backend Overhead):**
   - The browser streams the PDF bytes directly to Amazon S3 via `PUT <upload_url>`.
   - **Why this matters:** The backend server handles 0 bytes of the file upload. 100 concurrent uploads consume zero FastAPI network bandwidth or RAM buffers.

3. **Event Notification to SQS:**
   - As soon as S3 receives the complete file, it fires an `s3:ObjectCreated:Put` event notification.
   - S3 pushes this JSON payload directly into Amazon SQS queue (`clouddoc-document-processing`).

4. **Background Worker Consumption (Long-Polling):**
   - Detached worker process calls `sqs.receive_message(WaitTimeSeconds=20, MaxNumberOfMessages=1)`.
   - Using **20-second long polling** eliminates wasted empty HTTP loops and slashes AWS API costs.
   - SQS makes the message invisible to any other workers for `VisibilityTimeout=60` seconds.

5. **Text Extraction & State Transition:**
   - Worker queries PostgreSQL: finds document by `object_key`.
   - Transitions `status` from `"pending"` $\to$ `"processing"`.
   - Worker downloads file bytes from S3 (`s3.get_object`).
   - PyMuPDF opens the PDF in memory (`fitz.open(stream=file_bytes)`) and extracts all textual content across all pages.
   - Worker writes the text into PostgreSQL and transitions `status` $\to$ `"completed"`.
   - Worker deletes the SQS message via `sqs.delete_message(ReceiptHandle)`.

6. **Client Notification (Polling):**
   - React Dashboard polls `GET /documents/{document_id}` until `status == "completed"`, then renders the extracted text.

---

## 🐘 3. Deep Dive into PostgreSQL

PostgreSQL is the single source of truth for CloudDoc. In interviews, expect deep questions on relational modeling, indexing, and concurrency:

### 3.1 Relational Schema Design
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    object_key VARCHAR(500) NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    extracted_text TEXT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 Key PostgreSQL Architectural Decisions

#### Why PostgreSQL over MongoDB / DynamoDB?
- **Strict ACID Transactions & State Machine:** Changing document states (`pending` $\to$ `processing` $\to$ `completed`) requires atomic guarantees. If worker processing fails, transactional rollbacks ensure we do not leave orphaned partial records.
- **Relational Integrity:** Foreign key constraint `FOREIGN KEY (user_id) REFERENCES users(id)` guarantees documents cannot exist without a valid user account.
- **Structured vs. Unstructured Balance:** Metadata (filenames, user IDs, timestamps) is strongly typed and relational, while PostgreSQL's `TEXT` column handles arbitrarily large document extracts without document size limits like DynamoDB's 400 KB item ceiling.

#### Indexing Strategy:
- `users(email)`: **B-Tree Unique Index**. Ensures $O(\log N)$ user lookups during authentication (`/auth/login`) and enforces uniqueness at the database level.
- `documents(user_id)`: **B-Tree Foreign Key Index**. When a user views their dashboard (`GET /documents`), the query filters by `WHERE user_id = :uid`. Without an index on `user_id`, PostgreSQL would execute an expensive full-table sequential scan.
- `documents(object_key)`: Queried by the background worker when an S3 event arrives. Because S3 keys are unique (`users/{id}/documents/{uuid}-{filename}`), this allows instant lookup.
- `documents(id)`: **Primary Key Index**. Fast single-document polling (`GET /documents/{id}`).

#### Status Lifecycle & Race Condition Defense:
- **What if a worker crashes while processing?**
  When a worker picks up an SQS message, SQS sets a `VisibilityTimeout=60s`. If the worker crashes or does not delete the message within 60 seconds, SQS re-delivers the message to another healthy worker. The new worker locates the document, re-runs extraction, and marks it completed.
- **Idempotency:** Updating `status = 'completed'` and `extracted_text = :text` is completely **idempotent**. Even if the message is re-delivered, running extraction a second time produces identical output without corrupting database state.

#### Connection Pooling with SQLAlchemy & Psycopg 3:
- In `backend/app/database.py`, we initialize:
  ```python
  engine = create_engine(settings.database_url, pool_pre_ping=True)
  ```
- **`pool_pre_ping=True`:** Prevents *"server closed the connection unexpectedly"* errors. Before borrowing a connection from the pool, SQLAlchemy issues a lightweight `SELECT 1` ping. If the connection died (e.g. EC2 network blip or PostgreSQL idle timeout), it seamlessly reconnects.

---

## 📚 4. Libraries & Tech Stack: Why Were They Chosen?

| Technology / Library | What It Is | Why We Chose It (The Engineering Reason) | Alternatives Considered & Why Rejected |
| :--- | :--- | :--- | :--- |
| **FastAPI** | Modern Python async web framework | Built-in asynchronous request handling, high concurrency via ASGI/Uvicorn, automatic OpenAPI documentation, and native Pydantic validation. | **Django / Flask**: Too heavyweight (Django) or lacks native async/Pydantic validation (Flask). |
| **PyMuPDF (`fitz`)** | High-performance C-based PDF library | **Speed.** Built on top of MuPDF (written in C). It is **10x to 50x faster** than pure Python parsers. Operates entirely in memory from byte streams (`fitz.open(stream=bytes)`). | **PyPDF / PDFMiner**: Pure Python, significantly slower on dense multi-page documents. <br>**Tesseract / OCR**: 100x slower, excessive CPU for digital PDFs with embedded text. |
| **Amazon S3** | Object storage | 99.999999999% (11 9's) durability. Presigned URLs allow direct browser uploads, completely offloading file upload bandwidth from the backend. | **Local disk / EBS**: Fails to scale horizontally across multiple instances; disk fills up quickly; single point of failure. |
| **Amazon SQS** | Distributed message queue | Fully managed, zero server maintenance, dead-simple event integration with S3 (`s3:ObjectCreated`). Built-in message visibility timeouts and retry mechanisms. | **Celery + Redis**: Requires provisioning, patching, and maintaining a Redis cluster, memory management, and sentinel failover. SQS is serverless and cost-free at idle. |
| **SQLAlchemy 2.0** | Python ORM & SQL toolkit | Safe parameterized queries (preventing SQL injection), declarative models, migration support, and connection pooling. | **Raw SQL (psycopg only)**: Error-prone, lacks automatic serialization and model relationship tracking. |
| **Pydantic v2** | Data validation & settings | Schema validation executed in Rust; strict typing for request/response payloads (`DocumentResponse`, `UploadUrlRequest`). | **Manual dictionary validation**: Tedious, brittle, and lacks automatic Swagger doc generation. |
| **Docker & Docker Compose** | Container orchestration | Reproducible, identical environments across local dev and EC2 Linux deployment. Clean network isolation for DB. | **Bare metal installation**: Dependency conflicts, inconsistent Python/PostgreSQL versions across environments. |

---

## ⚡ 5. Benchmark Insights: Why Asynchronous Wins

In an interview, you should explain the difference between **API Latency** and **End-to-End Processing Duration**:

### Myth vs. Reality
- ❌ **Myth:** *"Asynchronous processing makes processing a single PDF faster."*
- ✅ **Reality:** *"Asynchronous processing actually adds a few seconds of coordination overhead (S3 notification $\to$ SQS $\to$ Worker polling $\to$ Client polling: ~3.7s vs ~18ms local direct extraction). **The real win is systemic scalability**: web server threads are never blocked by CPU-heavy extraction."*

### The Quantified Proof from Our Benchmark:
1. **$O(1)$ API Latency:**
   - In a **synchronous** architecture, the API blocks until PyMuPDF finishes. As document size increased from 1 page to 20 pages, execution time grew from **6.24 ms to 18.34 ms (+193.9%)**. Under 50 concurrent uploads, web server worker threads would starve, leading to HTTP 504 Gateway Timeouts.
   - In CloudDoc's **asynchronous** model, the API only writes a pending row and generates a presigned URL. The API latency was **p50 = 643 ms** across the transcontinental WAN, remaining virtually unchanged regardless of whether the document had 1 page or 20 pages.
2. **Zero Queue Backlog:**
   - Under batch load (10 concurrent documents), SQS backlog stayed at **0 messages accumulated**, proving the worker consumed tasks as rapidly as they arrived without system degradation.

---

## 🎤 6. Top 8 Interview Questions & Bulletproof Answers

### Q1: "Why use Presigned S3 URLs instead of uploading files through your FastAPI server?"
> *"Uploading files directly to FastAPI means binary data must travel through our Nginx proxy and FastAPI Python process. For a 50 MB PDF, that buffers 50 MB in web server RAM, occupies a worker thread for the entire upload duration, and consumes EC2 network bandwidth.
> By generating a presigned S3 PUT URL, the backend only handles a tiny JSON request (~1 KB). S3 handles the multi-megabyte binary transfer directly with its global network edge. This eliminates backend bandwidth costs and prevents Denial-of-Service attacks from slow uploads."*

### Q2: "What happens if two workers poll SQS and receive the same message?"
> *"SQS guarantees **at-least-once delivery**. When Worker A polls a message, SQS initiates a **Visibility Timeout** (configured to 60 seconds), hiding the message from Worker B. 
> If Worker A successfully processes the PDF within 60 seconds, it explicitly deletes the message from the queue, so Worker B never sees it. 
> If Worker A crashes or takes longer than 60 seconds, SQS makes the message visible again. In CloudDoc, our database updates are **idempotent**: running text extraction a second time simply overwrites the `extracted_text` and sets `status = 'completed'` with the exact same data, ensuring no corrupt or duplicate records."*

### Q3: "How does the client know when the PDF is finished processing?"
> *"In the current implementation, the frontend uses short-polling: once the upload to S3 succeeds, it queries `GET /documents/{document_id}` every 5 seconds until the status changes from `pending` or `processing` to `completed`.
> If scaling to thousands of concurrent users, short-polling introduces unnecessary HTTP traffic. In that scenario, I would upgrade the notification channel to **WebSockets** or **Server-Sent Events (SSE)** via AWS API Gateway WebSocket API or AWS AppSync, pushing a real-time event directly to the client when the worker completes."*

### Q4: "How does the background worker authenticate with AWS on EC2 without hardcoded secrets?"
> *"We follow the principle of least privilege using **AWS IAM Roles for EC2 Instances** (`CloudDoc-EC2-Profile`). 
> The EC2 instance automatically queries the AWS Instance Metadata Service (IMDSv2) to retrieve temporary credentials that rotate automatically. Boto3 detects these credentials transparently, meaning our `.env` files contain zero AWS access keys or secrets, completely mitigating credential leakage risks."*

### Q5: "What if someone uploads a non-PDF file, a malicious script, or a corrupted file?"
> *"We implement defense-in-depth across three layers:
> 1. **API Validation:** `POST /documents/upload-url` enforces an allowlist check: `request.content_type in {'application/pdf', 'text/plain'}`. If invalid, it rejects with HTTP 400 immediately.
> 2. **Filename Sanitization:** We use regex regex sanitization (`re.sub(r'[^a-zA-Z0-9.\-_]', '_', filename)`) and prefix a unique UUID to prevent directory traversal and S3 key collisions.
> 3. **Worker Error Handling:** When PyMuPDF parses the stream, if the file is corrupted or an executable renamed as `.pdf`, `fitz.open()` raises an exception. The worker catches this, sets `document.status = 'failed'`, records the exact error message in `document.error_message`, and safely commits, preventing the worker process from crashing."*

### Q6: "How would you handle a Dead Letter Queue (DLQ) in this architecture?"
> *"In production, if a corrupted PDF causes a worker to crash repeatedly without catching the exception, SQS would continually re-deliver the message, creating a 'poison pill' loop.
> To prevent this, we configure an SQS **Dead Letter Queue (DLQ)** with a `maxReceiveCount = 3`. If a message fails processing 3 times, SQS automatically moves it to the DLQ. We can set up an Amazon CloudWatch Alarm on the DLQ depth to alert on-call engineers via SNS without blocking the main processing pipeline."*

### Q7: "How would you scale CloudDoc to handle 100,000 PDFs per day?"
> *"To handle 100k PDFs/day (~70 PDFs/minute average, with peak spikes of 300+/min):
> 1. **Horizontal Worker Auto-Scaling:** Move the background worker from a single Docker container on EC2 to **AWS ECS (Elastic Container Service) with Fargate** or **AWS Lambda**. Configure an Auto Scaling Policy based on the SQS metric `ApproximateNumberOfMessagesVisible`.
> 2. **Database Connection Pooling:** When scaling to dozens of worker containers, database connections can exhaust PostgreSQL's `max_connections`. We would introduce **PgBouncer** or **AWS RDS Proxy** to pool database connections efficiently.
> 3. **Read Replicas:** Route document status reads (`GET /documents`) to read replicas while directing writes to the primary database."*

### Q8: "Why not use FastAPI BackgroundTasks instead of SQS and a separate worker?"
> *"FastAPI `BackgroundTasks` run inside the **same Python process and memory space as the web server**. 
> If 20 users upload complex PDFs at the same time, `BackgroundTasks` will peg the server's CPU cores at 100%, causing the event loop to lag and new incoming HTTP requests (like login or health checks) to drop or time out. 
> Furthermore, if the web container restarts or crashes, all pending in-memory background tasks are permanently lost. An external queue like SQS provides **fault tolerance, durability, and true process isolation**."*
