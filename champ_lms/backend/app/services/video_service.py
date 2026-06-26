import boto3
import time
import uuid
from botocore.signers import CloudFrontSigner
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from app.core.config import get_settings

settings = get_settings()


def _rsa_signer(message: bytes) -> bytes:
    private_key = serialization.load_pem_private_key(
        settings.cloudfront_private_key.replace("\\n", "\n").encode(),
        password=None,
    )
    return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())


def generate_cloudfront_signed_url(hls_manifest_key: str) -> str:
    if not settings.cloudfront_domain or not settings.cloudfront_key_pair_id:
        # Local dev: return direct S3-style path
        return f"http://localhost:9000/{settings.s3_hls_bucket}/{hls_manifest_key}"

    cf_signer = CloudFrontSigner(settings.cloudfront_key_pair_id, _rsa_signer)
    url = f"https://{settings.cloudfront_domain}/{hls_manifest_key}"
    expire = int(time.time()) + settings.cloudfront_signed_url_ttl_seconds
    return cf_signer.generate_presigned_url(url, date_less_than=expire)


def generate_s3_upload_presign(episode_id: uuid.UUID, content_type: str = "video/mp4") -> dict:
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )
    key = f"raw/{episode_id}.mp4"
    presigned = s3.generate_presigned_post(
        Bucket=settings.s3_raw_bucket,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[{"Content-Type": content_type}],
        ExpiresIn=900,  # 15 minutes
    )
    return {"upload_url": presigned["url"], "fields": presigned["fields"], "s3_key": key}


def generate_thumbnail_url(thumbnail_key: str) -> str | None:
    if not thumbnail_key:
        return None
    if not settings.cloudfront_domain:
        return f"http://localhost:9000/{settings.s3_thumbnails_bucket}/{thumbnail_key}"
    return f"https://{settings.cloudfront_domain}/{thumbnail_key}"
