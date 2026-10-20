"""Thin, testable wrapper around boto3's S3 client.

Works against AWS S3 or any S3-compatible store (MinIO locally). Two clients are
kept: one for server-to-S3 traffic, and one whose endpoint is the address a
*browser* can reach - presigned URLs are signed for the host they will be sent to,
so signing with the internal docker hostname would produce URLs that fail.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from flask import current_app

mimetypes.add_type("application/vnd.apple.mpegurl", ".m3u8")
mimetypes.add_type("video/mp2t", ".ts")
mimetypes.add_type("video/iso.segment", ".m4s")
mimetypes.add_type("text/vtt", ".vtt")


class S3Storage:
    def __init__(self, config: dict):
        self.raw_bucket = config["RAW_BUCKET"]
        self.media_bucket = config["MEDIA_BUCKET"]
        self.presign_ttl = config["PRESIGN_TTL_SECONDS"]
        endpoint = config.get("S3_ENDPOINT_URL")
        public_endpoint = config.get("S3_PUBLIC_ENDPOINT_URL") or endpoint
        boto_cfg = BotoConfig(
            signature_version="s3v4",
            retries={"max_attempts": 5, "mode": "adaptive"},
            # Path-style addressing is required by MinIO and harmless on AWS.
            s3={"addressing_style": "path"} if endpoint else {},
        )
        session = boto3.session.Session()
        kwargs = {"region_name": config["AWS_REGION"], "config": boto_cfg}
        self.client = session.client("s3", endpoint_url=endpoint, **kwargs)
        self.public_client = session.client("s3", endpoint_url=public_endpoint, **kwargs)

    # ------------------------------------------------------------------ setup
    def ensure_buckets(self) -> None:
        """Local/dev only (on AWS, Terraform owns the buckets)."""
        for bucket in (self.raw_bucket, self.media_bucket):
            try:
                self.client.head_bucket(Bucket=bucket)
            except ClientError:
                self.client.create_bucket(Bucket=bucket)
        # Browsers PUT upload parts straight to the raw bucket, cross-origin.
        try:
            self.client.put_bucket_cors(
                Bucket=self.raw_bucket,
                CORSConfiguration={"CORSRules": [{
                    "AllowedMethods": ["PUT", "GET", "HEAD"], "AllowedOrigins": ["*"],
                    "AllowedHeaders": ["*"], "ExposeHeaders": ["ETag"], "MaxAgeSeconds": 3000,
                }]},
            )
        except ClientError:
            pass  # e.g. MinIO, which allows all origins by default and rejects this call

    def ping(self) -> bool:
        self.client.head_bucket(Bucket=self.media_bucket)
        return True

    # ------------------------------------------------- multipart (raw bucket)
    def create_multipart_upload(self, key: str, content_type: str) -> str:
        resp = self.client.create_multipart_upload(
            Bucket=self.raw_bucket, Key=key, ContentType=content_type
        )
        return resp["UploadId"]

    def presign_part(self, key: str, upload_id: str, part_number: int) -> str:
        return self.public_client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.raw_bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=self.presign_ttl,
        )

    def list_parts(self, key: str, upload_id: str) -> list[dict]:
        """All parts S3 has received so far (paginated - S3 returns <=1000)."""
        parts: list[dict] = []
        marker = 0
        while True:
            resp = self.client.list_parts(
                Bucket=self.raw_bucket, Key=key, UploadId=upload_id, PartNumberMarker=marker
            )
            parts.extend(
                {"PartNumber": p["PartNumber"], "ETag": p["ETag"], "Size": p["Size"]}
                for p in resp.get("Parts", [])
            )
            if not resp.get("IsTruncated"):
                return parts
            marker = resp["NextPartNumberMarker"]

    def complete_multipart_upload(self, key: str, upload_id: str, parts: list[dict]) -> None:
        self.client.complete_multipart_upload(
            Bucket=self.raw_bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [{"PartNumber": p["PartNumber"], "ETag": p["ETag"]} for p in parts]
            },
        )

    def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        try:
            self.client.abort_multipart_upload(Bucket=self.raw_bucket, Key=key, UploadId=upload_id)
        except ClientError:
            pass  # already completed or aborted

    # -------------------------------------------------------------- objects
    def object_size(self, bucket: str, key: str) -> int | None:
        try:
            return self.client.head_object(Bucket=bucket, Key=key)["ContentLength"]
        except ClientError:
            return None

    def download_file(self, bucket: str, key: str, dest: str | Path) -> None:
        self.client.download_file(bucket, key, str(dest))

    def upload_file(
        self, path: str | Path, bucket: str, key: str, cache_control: str | None = None
    ) -> None:
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        extra = {"ContentType": content_type}
        if cache_control:
            extra["CacheControl"] = cache_control
        self.client.upload_file(str(path), bucket, key, ExtraArgs=extra)

    def iter_keys(self, bucket: str, prefix: str) -> Iterator[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"]

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        keys = list(self.iter_keys(bucket, prefix))
        for i in range(0, len(keys), 1000):  # DeleteObjects takes <=1000 keys
            batch = [{"Key": k} for k in keys[i : i + 1000]]
            self.client.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True})
        return len(keys)

    def delete_object(self, bucket: str, key: str) -> None:
        self.client.delete_object(Bucket=bucket, Key=key)

    def presign_get(self, bucket: str, key: str, ttl: int | None = None) -> str:
        return self.public_client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=ttl or self.presign_ttl
        )


def get_storage() -> S3Storage:
    return current_app.extensions["storage"]
