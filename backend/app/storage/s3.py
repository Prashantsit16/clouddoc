import boto3
from botocore.exceptions import ClientError
from pydantic_settings import BaseSettings, SettingsConfigDict

class StorageSettings(BaseSettings):
    aws_region: str = "us-east-1"
    aws_s3_bucket: str = "clouddoc-storage"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = StorageSettings()

def get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        # Boto3 will automatically pick up AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY 
        # from environment variables or IAM roles.
    )

def generate_presigned_upload_url(object_key: str, content_type: str, expiration: int = 600) -> str:
    """
    Generate a presigned URL for an S3 PUT operation.
    """
    s3_client = get_s3_client()
    try:
        response = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.aws_s3_bucket,
                "Key": object_key,
                "ContentType": content_type
            },
            ExpiresIn=expiration
        )
        return response
    except ClientError as e:
        # We don't want to expose internal AWS errors directly, just log or raise generic exception
        raise RuntimeError(f"Failed to generate presigned URL") from e
