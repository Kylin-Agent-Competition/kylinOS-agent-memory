"""providers 包 — 轨道 A Provider 层（Day4 骨架）。"""

from .embedding_provider import (
    EmbeddingProvider,
    EmbeddingResult,
    ModelInfo,
    ProviderError,
    ProviderErrorCode,
)

__all__ = [
    "EmbeddingProvider",
    "EmbeddingResult",
    "ModelInfo",
    "ProviderError",
    "ProviderErrorCode",
]
