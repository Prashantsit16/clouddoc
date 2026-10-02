import json
import logging
import sys
import os
import time

import boto3
import fitz  # PyMuPDF
from botocore.exceptions import ClientError
from pydantic_settings import BaseSettings, SettingsConfigDict

# Add backend directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.document import Document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class WorkerSettings(BaseSettings):
    aws_region: str = "us-east-1"
    aws_sqs_queue_name: str = "clouddoc-document-processing"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = WorkerSettings()

def get_queue_url(sqs_client, queue_name):
    try:
        response = sqs_client.get_queue_url(QueueName=queue_name)
        return response["QueueUrl"]
    except ClientError as e:
        logger.error(f"Failed to get Queue URL for {queue_name}: {e}")
        raise

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = ""
    try:
        # Open the PDF from memory
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text.strip()
    except Exception as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        raise ValueError("Invalid or corrupted PDF file") from e

def process_message(msg, sqs_client, s3_client, queue_url):
    body = msg.get("Body")
    receipt_handle = msg.get("ReceiptHandle")
    
    if not body:
        logger.warning("Empty message body, skipping.")
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Message body is not valid JSON, deleting message.")
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return

    # Handle test events (like s3:TestEvent)
    if "Event" in event and event["Event"] == "s3:TestEvent":
        logger.info("Received S3 Test Event, deleting.")
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return

    records = event.get("Records", [])
    if not records:
        logger.warning("No records found in event, deleting message.")
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return

    for record in records:
        event_name = record.get("eventName", "")
        if not event_name.startswith("ObjectCreated:"):
            logger.info(f"Ignoring non-creation event: {event_name}")
            continue

        try:
            s3_data = record["s3"]
            bucket_name = s3_data["bucket"]["name"]
            object_key = s3_data["object"]["key"]
            
            # S3 object keys might be URL-encoded (e.g., spaces replaced by +)
            # urllib.parse.unquote_plus can decode them if necessary.
            import urllib.parse
            object_key = urllib.parse.unquote_plus(object_key)
            
            logger.info(f"Processing object: {bucket_name}/{object_key}")
        except KeyError as e:
            logger.warning(f"Malformed S3 record missing key {e}, skipping record.")
            continue
            
        process_document(object_key, bucket_name, s3_client)
        
    # If we got here and didn't raise an exception inside process_document, 
    # we consider the message processed successfully (or safely skipped).
    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
    logger.info("Message processed and deleted from SQS.")

def process_document(object_key: str, bucket_name: str, s3_client):
    db = SessionLocal()
    try:
        # 1. Locate Document in DB
        document = db.query(Document).filter(Document.object_key == object_key).first()
        if not document:
            # We don't have this document in DB. This means the S3 upload wasn't initiated by our backend 
            # or the DB transaction didn't commit successfully. Log and skip.
            logger.error(f"Document with object_key '{object_key}' not found in database.")
            # We raise so the message isn't deleted, allowing redelivery if it's a race condition.
            # But normally S3 upload happens after DB commit, so it should be there.
            raise ValueError(f"Document not found for {object_key}")
            
        # 2. Update status to processing
        document.status = "processing"
        db.commit()
        logger.info(f"Document {document.id} status set to processing. S3 Bucket: {bucket_name}, DB Object Key: {object_key}, Worker Download Key: {object_key}")

        # 3. Download object from S3
        try:
            logger.info(f"Worker attempting to download exactly: s3://{bucket_name}/{object_key}")
            s3_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            file_bytes = s3_response["Body"].read()
        except ClientError as e:
            logger.error(f"Failed to download from S3: {e}")
            raise

        # 4. Extract Text
        extracted_text = extract_text_from_pdf(file_bytes)
        
        # 5. Save and complete
        document.extracted_text = extracted_text
        document.status = "completed"
        document.error_message = None
        db.commit()
        logger.info(f"Document {document.id} processed successfully.")

    except Exception as e:
        logger.error(f"Error processing document {object_key}: {e}")
        # Mark as failed in DB
        try:
            db.rollback() # Ensure transaction is clean
            doc = db.query(Document).filter(Document.object_key == object_key).first()
            if doc:
                doc.status = "failed"
                doc.error_message = str(e)
                db.commit()
                logger.info(f"Document {doc.id} marked as failed in database.")
        except Exception as db_err:
            logger.error(f"Failed to update database error state: {db_err}")
            
        # Re-raise so the outer loop does NOT delete the SQS message
        raise
    finally:
        db.close()

def run_worker():
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    s3 = boto3.client("s3", region_name=settings.aws_region)
    
    queue_url = get_queue_url(sqs, settings.aws_sqs_queue_name)
    logger.info(f"Starting worker. Polling SQS queue: {queue_url}")
    
    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20, # Long polling
                VisibilityTimeout=60 # Hide message from other workers for 60 seconds
            )
            
            messages = response.get("Messages", [])
            for msg in messages:
                process_message(msg, sqs, s3, queue_url)
                
        except KeyboardInterrupt:
            logger.info("Worker stopped by user.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in polling loop: {e}")
            time.sleep(5) # Backoff before retrying

if __name__ == "__main__":
    run_worker()
