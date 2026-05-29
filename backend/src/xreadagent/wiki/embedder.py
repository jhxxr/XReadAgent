# SPDX-License-Identifier: AGPL-3.0-or-later
"""Embedding engine for wiki pages -- ONNX Runtime, no torch.

Uses ``optimum.onnxruntime`` to load a sentence-transformers ONNX model.
The model is lazy-loaded on first use so ``import xreadagent`` stays
near-instant even when the embedding deps are installed.

Model cache directory: ``~/.xreadagent/models/embeddings/<model_name>/``.
First use triggers a download (~130 MB for ``all-MiniLM-L6-v2``); subsequent
uses hit the local cache.

Embedding failures raise :class:`EmbeddingError` -- callers should catch it
and degrade gracefully (log warning, skip vector upsert, continue).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

_logger = logging.getLogger(__name__)

_DEFAULT_MODEL: Final[str] = "all-MiniLM-L6-v2"
_DEFAULT_DIMENSION: Final[int] = 384
_MODEL_CACHE_BASE: Final[str] = ".xreadagent/models/embeddings"


class EmbeddingError(Exception):
    """Raised when embedding computation fails.

    Callers should catch this and degrade gracefully -- log a warning and
    continue without vector search rather than crashing the ingest.
    """


class Embedder:
    """ONNX-backed text embedder. Lazy-loads the model on first use.

    Parameters
    ----------
    model_name
        HuggingFace model identifier. Must have ONNX weights available.
    dimension
        Embedding dimension. Must match the model's output. 384 for
        ``all-MiniLM-L6-v2``, 768 for ``specter2_base``.
    cache_dir
        Override the default model cache directory. Defaults to
        ``~/.xreadagent/models/embeddings/<model_name>/``.
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        dimension: int = _DEFAULT_DIMENSION,
        cache_dir: Path | None = None,
    ) -> None:
        self._model_name = model_name
        self._dimension = dimension
        self._cache_dir = cache_dir
        self._model: object | None = None
        self._tokenizer: object | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _ensure_loaded(self) -> None:
        """Load the ONNX model and tokenizer on first use."""
        if self._model is not None:
            return

        try:
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise EmbeddingError(
                "optimum[onnxruntime] and transformers are required for embedding. "
                "Install via: pip install 'optimum[onnxruntime]' transformers"
            ) from exc

        cache = self._cache_dir or (Path.home() / _MODEL_CACHE_BASE / self._model_name)

        try:
            _logger.info(
                "loading embedding model %s (cache: %s)",
                self._model_name,
                cache,
            )
            self._tokenizer = AutoTokenizer.from_pretrained(  # type: ignore[no-untyped-call]
                self._model_name, cache_dir=str(cache)
            )
            self._model = ORTModelForFeatureExtraction.from_pretrained(
                self._model_name, cache_dir=str(cache)
            )
            _logger.info("embedding model loaded: %s", self._model_name)
        except Exception as exc:
            self._model = None
            self._tokenizer = None
            raise EmbeddingError(
                f"failed to load embedding model '{self._model_name}': {exc}"
            ) from exc

    def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns a list of floats.

        Raises :class:`EmbeddingError` on any failure.
        """
        results = self.embed_batch([text])
        return results[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings. Returns a list of float lists.

        Uses ONNX Runtime for inference (no torch dependency) and numpy for
        post-processing (mean-pooling + L2 normalization).

        Raises :class:`EmbeddingError` on any failure.
        """
        if not texts:
            return []

        self._ensure_loaded()
        assert self._model is not None
        assert self._tokenizer is not None

        try:
            import numpy as np
        except ImportError as exc:
            raise EmbeddingError(
                "numpy is required for embedding post-processing"
            ) from exc

        try:
            encoded = self._tokenizer(  # type: ignore[operator]
                texts,
                padding=True,
                truncation=True,
                return_tensors="np",  # numpy arrays, not torch tensors
            )
            outputs = self._model(**encoded)  # type: ignore[operator]

            # Mean-pool over the token dimension, using attention mask.
            # All operations use numpy — no torch dependency.
            token_embeddings = np.array(outputs.last_hidden_state)
            attention_mask = np.array(encoded["attention_mask"])
            # Expand mask to match embedding dimensions: (batch, seq_len, dim)
            input_mask_expanded = np.broadcast_to(
                attention_mask[:, :, np.newaxis], token_embeddings.shape
            ).astype(np.float32)
            sum_embeddings = np.sum(
                token_embeddings * input_mask_expanded, axis=1
            )
            sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
            mean_embeddings = sum_embeddings / sum_mask

            # Normalize to unit length.
            norms = np.linalg.norm(mean_embeddings, ord=2, axis=1, keepdims=True)
            norms = np.clip(norms, a_min=1e-9, a_max=None)
            normalized = mean_embeddings / norms

            return [row.tolist() for row in normalized]
        except Exception as exc:
            raise EmbeddingError(f"embedding inference failed: {exc}") from exc


__all__ = ["Embedder", "EmbeddingError"]
