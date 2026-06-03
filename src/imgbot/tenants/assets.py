"""Tenant binary-asset storage on Supabase Storage.

Handles logos, sample posters, and generated posters. We mirror logos under
`data/tenants/<phone>/logo.<ext>` so the runtime pipeline doesn't pay a
network round-trip just to fetch the logo on every generation.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from PIL import Image

from imgbot import config
from imgbot.tenants.schema import normalize_phone
from imgbot.tenants.store import _client


LOGO_BUCKET = "tenant-logos"
SAMPLE_BUCKET = "tenant-samples"
POSTER_BUCKET = "tenant-posters"


def _ext_for_bytes(image_bytes: bytes, default: str = "png") -> str:
    fmt = (Image.open(io.BytesIO(image_bytes)).format or "").lower()
    return {"png": "png", "jpeg": "jpg", "webp": "webp", "gif": "gif"}.get(fmt, default)


def _content_type_for_ext(ext: str) -> str:
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext.lower(), "application/octet-stream")


def _tenant_cache_dir(phone: str) -> Path:
    d = config.TENANTS_CACHE / normalize_phone(phone)
    d.mkdir(parents=True, exist_ok=True)
    return d


class AssetStore:
    """Upload / download helpers around Supabase Storage."""

    def __init__(self):
        self._storage = _client().storage

    # -- upload ------------------------------------------------------------- #
    def upload_logo(self, phone: str, image_bytes: bytes) -> str:
        phone = normalize_phone(phone)
        ext = _ext_for_bytes(image_bytes, "png")
        path = f"{phone}/logo.{ext}"
        self._storage.from_(LOGO_BUCKET).upload(
            path,
            image_bytes,
            file_options={"content-type": _content_type_for_ext(ext), "upsert": "true"},
        )
        # Mirror locally so runtime can skip the round-trip.
        (_tenant_cache_dir(phone) / f"logo.{ext}").write_bytes(image_bytes)
        return path

    def upload_sample(self, phone: str, index: int, image_bytes: bytes) -> str:
        phone = normalize_phone(phone)
        ext = _ext_for_bytes(image_bytes, "jpg")
        path = f"{phone}/sample_{index:02d}.{ext}"
        self._storage.from_(SAMPLE_BUCKET).upload(
            path,
            image_bytes,
            file_options={"content-type": _content_type_for_ext(ext), "upsert": "true"},
        )
        return path

    def upload_poster_pair(
        self, phone: str, basename: str, *, raw: bytes, final: bytes
    ) -> tuple[str, str]:
        phone = normalize_phone(phone)
        raw_path = f"{phone}/{basename}.raw.png"
        final_path = f"{phone}/{basename}.final.png"
        opts = {"content-type": "image/png", "upsert": "true"}
        self._storage.from_(POSTER_BUCKET).upload(raw_path, raw, file_options=opts)
        self._storage.from_(POSTER_BUCKET).upload(final_path, final, file_options=opts)
        return raw_path, final_path

    # -- download ----------------------------------------------------------- #
    def download(self, bucket: str, path: str) -> bytes:
        return self._storage.from_(bucket).download(path)

    def get_logo_bytes(self, phone: str, logo_path: str, *, use_cache: bool = True) -> bytes:
        """Return the tenant's logo bytes. Hits the local mirror first when
        possible, otherwise pulls from Storage and refreshes the mirror."""
        phone = normalize_phone(phone)
        cache_dir = _tenant_cache_dir(phone)
        cached = cache_dir / Path(logo_path).name
        if use_cache and cached.exists():
            return cached.read_bytes()
        data = self.download(LOGO_BUCKET, logo_path)
        cached.write_bytes(data)
        return data

    def save_poster_local(
        self, phone: str, basename: str, *, raw: bytes, final: bytes
    ) -> tuple[Path, Path]:
        """Also drop a local copy of each generated poster so the WhatsApp bot
        can `MessageMedia.fromFilePath` without re-downloading."""
        phone = normalize_phone(phone)
        out_dir = _tenant_cache_dir(phone) / "posters"
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_p = out_dir / f"{basename}.raw.png"
        final_p = out_dir / f"{basename}.final.png"
        raw_p.write_bytes(raw)
        final_p.write_bytes(final)
        return raw_p, final_p

    def signed_url(self, bucket: str, path: str, expires_in_seconds: int = 3600) -> str:
        result = self._storage.from_(bucket).create_signed_url(path, expires_in_seconds)
        # supabase-py returns {"signedURL": "https://..."} on v2
        return result.get("signedURL") or result.get("signed_url") or ""
