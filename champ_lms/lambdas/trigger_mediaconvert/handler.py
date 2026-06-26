"""
Lambda #1 — Triggers MediaConvert when a raw video lands in S3.
Trigger: S3 ObjectCreated on champ-lms-raw-videos bucket.
"""
import os
import json
import uuid
import boto3

MEDIACONVERT_ENDPOINT = os.environ["MEDIACONVERT_ENDPOINT"]
MEDIACONVERT_ROLE_ARN = os.environ["MEDIACONVERT_ROLE_ARN"]
HLS_BUCKET = os.environ["HLS_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")


def handler(event, context):
    mc = boto3.client("mediaconvert", endpoint_url=MEDIACONVERT_ENDPOINT, region_name=AWS_REGION)

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        # key format: raw/{episode_id}.mp4
        episode_id = key.split("/")[-1].replace(".mp4", "")
        output_prefix = f"hls/{episode_id}/"

        job_settings = {
            "Role": MEDIACONVERT_ROLE_ARN,
            "Settings": {
                "Inputs": [{
                    "FileInput": f"s3://{bucket}/{key}",
                    "AudioSelectors": {"Audio Selector 1": {"DefaultSelection": "DEFAULT"}},
                }],
                "OutputGroups": [{
                    "Name": "HLS",
                    "OutputGroupSettings": {
                        "Type": "HLS_GROUP_SETTINGS",
                        "HlsGroupSettings": {
                            "Destination": f"s3://{HLS_BUCKET}/{output_prefix}",
                            "SegmentLength": 6,
                            "MinSegmentLength": 0,
                        },
                    },
                    "Outputs": [
                        _hls_output("360p", 640, 360, 800_000),
                        _hls_output("720p", 1280, 720, 2_500_000),
                        _hls_output("1080p", 1920, 1080, 5_000_000),
                    ],
                }],
            },
            "UserMetadata": {"episode_id": episode_id},
        }

        mc.create_job(**job_settings)
        print(f"MediaConvert job created for episode {episode_id}")

    return {"statusCode": 200}


def _hls_output(label: str, width: int, height: int, bitrate: int) -> dict:
    return {
        "NameModifier": f"_{label}",
        "VideoDescription": {
            "Width": width,
            "Height": height,
            "CodecSettings": {
                "Codec": "H_264",
                "H264Settings": {
                    "Bitrate": bitrate,
                    "RateControlMode": "CBR",
                    "CodecProfile": "HIGH",
                    "CodecLevel": "AUTO",
                },
            },
        },
        "AudioDescriptions": [{
            "CodecSettings": {
                "Codec": "AAC",
                "AacSettings": {"Bitrate": 96000, "SampleRate": 48000},
            }
        }],
        "OutputSettings": {"HlsSettings": {}},
        "ContainerSettings": {"Container": "M3U8"},
    }
