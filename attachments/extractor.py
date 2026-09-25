"""Bounded, dependency-optional extraction for user attachments.

This module produces context for the governed chat layer. It never executes
content from an attachment and never sends non-image bytes to a provider.
Optional libraries add depth when installed; the safe metadata path remains
available in a minimal deployment.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import mimetypes
import os
import struct
import tempfile
import wave
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARS = 24_000
MAX_ZIP_MEMBERS = 2_000


@dataclass(frozen=True)
class AttachmentInput:
    data: bytes
    mime_type: str = "application/octet-stream"
    filename: str = "attachment"


@dataclass(frozen=True)
class ExtractionResult:
    filename: str
    mime_type: str
    kind: str
    text: str
    metadata: dict
    available: bool = True

    @property
    def context(self) -> str:
        lines = [
            f"ATTACHMENT: {self.filename}",
            f"MIME: {self.mime_type}",
            f"TYPE: {self.kind}",
        ]
        for key, value in self.metadata.items():
            lines.append(f"{key}: {value}")
        if self.text:
            lines.extend(("EXTRACTED CONTENT:", self.text))
        elif not self.available:
            lines.append("EXTRACTION: This format needs an optional local extractor.")
        return "\n".join(lines)


def _clip(text: str) -> str:
    text = (text or "").replace("\x00", "").strip()
    if len(text) > MAX_EXTRACTED_CHARS:
        return text[:MAX_EXTRACTED_CHARS] + "\n[extraction clipped]"
    return text


def _kind(mime: str, filename: str, data: bytes) -> str:
    lowered = f"{mime} {filename}".lower()
    if data.startswith(b"%PDF-") or "pdf" in lowered:
        return "pdf"
    if data.startswith(b"PK\x03\x04") and filename.lower().endswith(".docx"):
        return "docx"
    if data.startswith(b"PK\x03\x04") and filename.lower().endswith(".apk"):
        return "apk"
    if mime.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    if mime.startswith("audio/") or filename.lower().endswith((".mp3", ".wav", ".ogg", ".m4a", ".flac")):
        return "audio"
    if mime.startswith("video/") or filename.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
        return "video"
    if filename.lower().endswith((".txt", ".md", ".log", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".csv")):
        return "text"
    return "binary"


def _text_content(data: bytes, filename: str) -> str:
    decoded = data.decode("utf-8", errors="replace")
    if filename.lower().endswith(".json"):
        try:
            return json.dumps(json.loads(decoded), indent=2, ensure_ascii=True)
        except json.JSONDecodeError:
            return decoded
    if filename.lower().endswith(".csv"):
        rows = list(csv.reader(io.StringIO(decoded)))[:200]
        return "\n".join(" | ".join(row) for row in rows)
    return decoded


def _docx_content(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    chunks = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "t" and node.text:
            chunks.append(node.text)
        elif node.tag.rsplit("}", 1)[-1] in {"p", "br"}:
            chunks.append("\n")
    return " ".join(chunks).replace(" \n ", "\n")


def _zip_metadata(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) > MAX_ZIP_MEMBERS:
            raise ValueError("archive contains too many members")
        return {
            "ZIP_MEMBERS": len(names),
            "ZIP_SAMPLE": ", ".join(names[:20]),
        }


def _image_metadata(data: bytes) -> dict:
    metadata = {"IMAGE_BYTES": len(data)}
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            metadata.update({
                "DIMENSIONS": f"{image.width}x{image.height}",
                "FORMAT": image.format or "unknown",
                "MODE": image.mode,
            })
    except Exception:
        pass
    if os.environ.get("LIONEL_ENABLE_OCR", "false").lower() == "true":
        try:
            import pytesseract
            from PIL import Image
            with Image.open(io.BytesIO(data)) as image:
                text = _clip(pytesseract.image_to_string(image))
            if text:
                metadata["OCR_TEXT"] = text
        except Exception:
            metadata["OCR"] = "optional OCR backend unavailable"
    return metadata


def _audio_metadata(data: bytes, mime: str) -> dict:
    metadata = {"AUDIO_BYTES": len(data), "AUDIO_MIME": mime}
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            metadata.update({
                "CHANNELS": wav.getnchannels(),
                "SAMPLE_RATE": wav.getframerate(),
                "DURATION_SECONDS": round(wav.getnframes() / max(wav.getframerate(), 1), 2),
            })
    except Exception:
        pass
    if os.environ.get("LIONEL_ENABLE_TRANSCRIPTION", "false").lower() == "true":
        try:
            from faster_whisper import WhisperModel
            model_name = os.environ.get("LIONEL_WHISPER_MODEL", "tiny")
            suffix = mimetypes.guess_extension(mime) or ".audio"
            with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
                handle.write(data)
                handle.flush()
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                segments, _ = model.transcribe(handle.name)
                transcript = _clip(" ".join(segment.text for segment in segments))
            if transcript:
                metadata["TRANSCRIPT"] = transcript
        except Exception:
            metadata["TRANSCRIPTION"] = "optional Whisper backend unavailable"
    return metadata


def _video_metadata(data: bytes, mime: str) -> dict:
    metadata = {
        "VIDEO_BYTES": len(data),
        "VIDEO_MIME": mime,
        "NOTE": "Frame extraction and transcription require an optional local media backend.",
    }
    try:
        import cv2
        suffix = mimetypes.guess_extension(mime) or ".video"
        with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
            handle.write(data)
            handle.flush()
            capture = cv2.VideoCapture(handle.name)
            metadata.update({
                "FRAME_COUNT": int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
                "FPS": round(float(capture.get(cv2.CAP_PROP_FPS) or 0), 2),
                "WIDTH": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
                "HEIGHT": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
            })
            capture.release()
    except Exception:
        metadata["VIDEO_BACKEND"] = "optional OpenCV backend unavailable"
    return metadata


def extract_attachment(attachment: AttachmentInput) -> ExtractionResult:
    """Inspect one bounded attachment without executing its contents."""
    filename = Path(attachment.filename or "attachment").name
    mime = (attachment.mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream").lower()
    data = attachment.data or b""
    kind = _kind(mime, filename, data)
    metadata = {"BYTES": len(data)}

    if len(data) > MAX_ATTACHMENT_BYTES:
        return ExtractionResult(filename, mime, kind, "", {**metadata, "LIMIT": "attachment too large"}, False)

    try:
        if kind == "text":
            return ExtractionResult(filename, mime, kind, _clip(_text_content(data, filename)), metadata)
        if kind == "docx":
            return ExtractionResult(filename, mime, kind, _clip(_docx_content(data)), metadata)
        if kind == "pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(data))
                metadata["PAGES"] = len(reader.pages)
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
                return ExtractionResult(filename, mime, kind, _clip(text), metadata)
            except ImportError:
                return ExtractionResult(filename, mime, kind, "", {**metadata, "PAGES": "unknown"}, False)
        if kind == "apk":
            metadata.update(_zip_metadata(data))
            return ExtractionResult(filename, mime, kind, "", metadata, False)
        if kind == "image":
            return ExtractionResult(filename, mime, kind, "", {**metadata, **_image_metadata(data)}, True)
        if kind == "audio":
            return ExtractionResult(filename, mime, kind, "", _audio_metadata(data, mime), False)
        if kind == "video":
            return ExtractionResult(filename, mime, kind, "", _video_metadata(data, mime), False)
        return ExtractionResult(filename, mime, kind, "", metadata, False)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        logger.warning("Attachment extraction failed for %s: %s", filename, type(exc).__name__)
        return ExtractionResult(filename, mime, kind, "", {**metadata, "ERROR": "format could not be inspected"}, False)
