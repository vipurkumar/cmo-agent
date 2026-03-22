"""BaseTool — abstract base class for all CMO Agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.ratelimit.bucket import RateLimiter


class BaseTool(ABC):
    """Every tool in the CMO Agent must extend this class.

    Subclasses MUST:
    - Accept a ``RateLimiter`` in ``__init__``
    - Call ``rate_limiter.enforce()`` before any HTTP call
    - Use ``httpx.AsyncClient`` with a timeout
    - Handle 429 and 401 status codes specifically
    - Use ``@retry`` from tenacity
    """

    def __init__(self, rate_limiter: RateLimiter) -> None:
        self.rate_limiter = rate_limiter

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool's primary action.

        Every implementation must enforce rate limits, use httpx with
        timeouts, and handle 429/401 errors explicitly.
        """
        ...
