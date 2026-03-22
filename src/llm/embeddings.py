"""Embedding generation for OmniGTM knowledge base and semantic search.

Supports Anthropic Voyage AI and OpenAI embeddings.
All embedding calls go through embed_text() and embed_batch().
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import settings
from src.logger import log

# The campaign_memory table uses vector(1536). If the embedding model produces
# fewer dimensions (e.g. voyage-3 = 1024), we pad with zeros for compatibility.
_DB_VECTOR_DIM = 1536


def _pad_vector(vector: list[float], target_dim: int = _DB_VECTOR_DIM) -> list[float]:
    """Pad a vector with trailing zeros to match the DB column dimension."""
    if len(vector) >= target_dim:
        return vector[:target_dim]
    return vector + [0.0] * (target_dim - len(vector))


def _zero_vector() -> list[float]:
    """Return a zero-vector fallback at the DB dimension."""
    return [0.0] * _DB_VECTOR_DIM


# ---------------------------------------------------------------------------
# Voyage AI (Anthropic) provider
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TransportError, Exception)),
)
async def _embed_voyage(
    texts: list[str],
    input_type: str = "document",
) -> list[list[float]]:
    """Call Voyage AI embedding API via the voyageai Python package."""
    import voyageai  # lazy import — only needed when provider is "anthropic"

    client = voyageai.AsyncClient(api_key=settings.ANTHROPIC_API_KEY)
    result = await client.embed(
        texts,
        model=settings.EMBEDDING_MODEL,
        input_type=input_type,
    )

    log.info(
        "embeddings.voyage.complete",
        provider="anthropic",
        model=settings.EMBEDDING_MODEL,
        input_type=input_type,
        text_count=len(texts),
        total_tokens=getattr(result, "total_tokens", None),
    )
    return [_pad_vector(v) for v in result.embeddings]


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
)
async def _embed_openai(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API directly via httpx."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.EMBEDDING_MODEL,
                "input": texts,
            },
        )
        resp.raise_for_status()

    data = resp.json()
    usage = data.get("usage", {})
    log.info(
        "embeddings.openai.complete",
        provider="openai",
        model=settings.EMBEDDING_MODEL,
        text_count=len(texts),
        total_tokens=usage.get("total_tokens"),
    )
    # OpenAI returns embeddings sorted by index
    sorted_items = sorted(data["data"], key=lambda x: x["index"])
    return [_pad_vector(item["embedding"]) for item in sorted_items]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def embed_text(text: str, input_type: str = "document") -> list[float]:
    """Embed a single text string.

    Parameters
    ----------
    text:
        The text to embed.
    input_type:
        Hint for the embedding model. Use ``"document"`` when storing content,
        ``"query"`` when searching. Only used by Voyage AI.

    Returns
    -------
    list[float]
        Embedding vector padded to ``_DB_VECTOR_DIM`` dimensions.
        Falls back to a zero vector on error.
    """
    try:
        vectors = await embed_batch([text], input_type=input_type, batch_size=1)
        return vectors[0]
    except Exception as exc:
        log.error(
            "embeddings.embed_text.failed",
            provider=settings.EMBEDDING_PROVIDER,
            model=settings.EMBEDDING_MODEL,
            error=str(exc),
        )
        return _zero_vector()


async def embed_batch(
    texts: list[str],
    input_type: str = "document",
    batch_size: int = 20,
) -> list[list[float]]:
    """Embed multiple texts, batching to avoid API limits.

    Parameters
    ----------
    texts:
        List of texts to embed.
    input_type:
        ``"document"`` for storage, ``"query"`` for search (Voyage AI only).
    batch_size:
        Maximum texts per API call.

    Returns
    -------
    list[list[float]]
        List of embedding vectors, each padded to ``_DB_VECTOR_DIM``.
        On error, returns zero vectors for all inputs.
    """
    if not texts:
        return []

    provider = settings.EMBEDDING_PROVIDER
    all_vectors: list[list[float]] = []

    try:
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            if provider == "anthropic":
                vectors = await _embed_voyage(batch, input_type=input_type)
            elif provider == "openai":
                vectors = await _embed_openai(batch)
            else:
                raise ValueError(f"Unknown embedding provider: {provider}")

            all_vectors.extend(vectors)

        log.info(
            "embeddings.embed_batch.complete",
            provider=provider,
            model=settings.EMBEDDING_MODEL,
            total_texts=len(texts),
            total_vectors=len(all_vectors),
        )
        return all_vectors

    except Exception as exc:
        log.error(
            "embeddings.embed_batch.failed",
            provider=provider,
            model=settings.EMBEDDING_MODEL,
            total_texts=len(texts),
            error=str(exc),
        )
        return [_zero_vector() for _ in texts]
