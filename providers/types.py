"""
Lionel Agent - Shared data types for providers.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    role: str
    content: str
    image_data: Optional[bytes] = None
    image_mime_type: str = "image/jpeg"


@dataclass
class Completion:
    text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached: bool = False
    raw: Optional[dict] = None


@dataclass
class ProviderError(Exception):
    provider: str
    model: str
    status_code: Optional[int]
    message: str
    retryable: bool = False
    permanent: bool = False