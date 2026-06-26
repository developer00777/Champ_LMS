from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Champ LMS API"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://dev:dev@db/champlms"

    # Redis
    redis_url: str = "redis://redis:6379"

    # AWS
    aws_region: str = "ap-south-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # S3
    s3_raw_bucket: str = "champ-lms-raw-videos"
    s3_hls_bucket: str = "champ-lms-hls"
    s3_thumbnails_bucket: str = "champ-lms-thumbnails"

    # CloudFront
    cloudfront_domain: str = ""
    cloudfront_key_pair_id: str = ""
    cloudfront_private_key: str = ""  # PEM string, newlines as \n
    cloudfront_signed_url_ttl_seconds: int = 14400  # 4 hours

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    cognito_region: str = "ap-south-1"

    # MediaConvert
    mediaconvert_endpoint: str = ""
    mediaconvert_role_arn: str = ""
    mediaconvert_queue_arn: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Zoom
    zoom_webhook_secret: str = ""
    zoom_account_id: str = ""
    zoom_client_id: str = ""
    zoom_client_secret: str = ""

    # SQS
    sqs_zoom_queue_url: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
