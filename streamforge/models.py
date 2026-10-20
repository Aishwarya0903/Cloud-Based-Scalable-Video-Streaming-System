from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


class VideoStatus:
    UPLOADING = "uploading"    # multipart upload in progress (browser -> S3)
    QUEUED = "queued"          # upload complete, waiting for a transcode worker
    PROCESSING = "processing"  # worker is building the HLS ladder
    READY = "ready"            # playable through the CDN
    FAILED = "failed"

    ALL = (UPLOADING, QUEUED, PROCESSING, READY, FAILED)


class Visibility:
    PUBLIC = "public"      # listed in the library
    UNLISTED = "unlisted"  # playable by anyone with the link
    PRIVATE = "private"    # owner only

    ALL = (PUBLIC, UNLISTED, PRIVATE)


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    videos: Mapped[list[Video]] = relationship(back_populates="owner")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {"id": self.id, "email": self.email, "display_name": self.display_name}


class Video(db.Model):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[str] = mapped_column(String(16), default=Visibility.PUBLIC)

    # lifecycle
    status: Mapped[str] = mapped_column(String(16), default=VideoStatus.UPLOADING, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100 transcode progress
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # upload
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    raw_key: Mapped[str] = mapped_column(String(512))
    upload_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    part_size: Mapped[int] = mapped_column(Integer)
    part_count: Mapped[int] = mapped_column(Integer)

    # media metadata (filled by the transcoder)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    renditions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    processing_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    ready_at: Mapped[datetime | None] = mapped_column(nullable=True)

    owner: Mapped[User] = relationship(back_populates="videos")

    @property
    def media_prefix(self) -> str:
        """Prefix under the media bucket that holds every derived asset."""
        return f"hls/{self.id}/"

    def can_view(self, user: User | None) -> bool:
        if user is not None and user.id == self.owner_id:
            return True
        return self.visibility != Visibility.PRIVATE and self.status == VideoStatus.READY

    def to_dict(self, private: bool = False) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "visibility": self.visibility,
            "status": self.status,
            "progress": round(self.progress or 0, 1),
            "duration_s": self.duration_s,
            "width": self.width,
            "height": self.height,
            "renditions": self.renditions or [],
            "view_count": self.view_count,
            "owner": {"id": self.owner_id, "display_name": self.owner.display_name},
            "created_at": self.created_at.isoformat() + "Z",
            "ready_at": self.ready_at.isoformat() + "Z" if self.ready_at else None,
        }
        if private:
            data.update(
                {
                    "original_filename": self.original_filename,
                    "size_bytes": self.size_bytes,
                    "error": self.error,
                    "processing_seconds": self.processing_seconds,
                }
            )
        return data


RETENTION_BUCKETS = 20  # 5% slices of the video


class PlaybackSession(db.Model):
    """One viewer watching one video once, built up from player beacons.

    Holds the quality-of-experience numbers a streaming team actually watches:
    startup time, rebuffering, quality switches, delivered bitrate and how far
    into the video people get (a bitmask of 5% slices -> audience retention).
    """

    __tablename__ = "playback_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # generated by the player
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    viewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    last_seen: Mapped[datetime] = mapped_column(default=utcnow)
    watch_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    startup_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rebuffer_count: Mapped[int] = mapped_column(Integer, default=0)
    rebuffer_ms: Mapped[int] = mapped_column(Integer, default=0)
    quality_switches: Mapped[int] = mapped_column(Integer, default=0)
    bitrate_sum: Mapped[float] = mapped_column(Float, default=0.0)  # bitrate x seconds, for a time-weighted mean
    watched_mask: Mapped[int] = mapped_column(BigInteger, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
