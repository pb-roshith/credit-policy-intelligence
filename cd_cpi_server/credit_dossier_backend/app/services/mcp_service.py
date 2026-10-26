import asyncio
import json
import logging
import os
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.shared.exceptions import McpError

from app.config import settings

logger = logging.getLogger(__name__)


# ── Typed Responses ────────────────────────────────────────────────

@dataclass
class DocumentSummary:
    """Parsed document summary from MCP server."""
    title: str
    doc_type: str = ""
    summary: str = ""
    company_name: str = ""


# ── Constants ──────────────────────────────────────────────────────

MCP_SSE_URL = os.getenv("MCP_SSE_URL", "http://127.0.0.1:8004/sse")
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0  # seconds, exponential backoff base


class MCPClientService:
    """
    MCP client with per-call connection pattern.

    Instead of holding a long-lived SSE connection, each tool call opens a fresh
    local connection, executes the tool, and closes the connection. This keeps
    backend restarts and local MCP restarts independent.

    Features:
    - Per-call SSE connections (no idle timeout issues)
    - Exponential backoff retry (up to MAX_RETRIES attempts)
    - Circuit breaker (stops hammering a dead server)
    - TTL cache for document summaries
    - Warm-up ping at startup to verify reachability
    """

    is_connected: bool = False  # Tracks whether the server is reachable

    # ── TTL Cache for document summaries ────────────────────────
    _summary_cache: Dict[str, tuple[str, float]] = {}  # key → (data, timestamp)
    _structured_cache: Dict[str, tuple[Dict[str, Any], float]] = {}

    # ── Circuit Breaker ────────────────────────────────────────
    _consecutive_failures: int = 0
    _circuit_open_until: float = 0.0  # timestamp

    @classmethod
    def _is_circuit_open(cls) -> bool:
        if cls._circuit_open_until > 0 and time.time() < cls._circuit_open_until:
            return True
        if cls._circuit_open_until > 0 and time.time() >= cls._circuit_open_until:
            # Reset circuit breaker — allow retry
            cls._circuit_open_until = 0.0
            cls._consecutive_failures = 0
        return False

    @classmethod
    def _record_failure(cls) -> None:
        cls._consecutive_failures += 1
        if cls._consecutive_failures >= settings.MCP_MAX_FAILURES:
            cls._circuit_open_until = time.time() + settings.MCP_CIRCUIT_BREAKER_SECONDS
            logger.warning(
                f"MCP circuit breaker OPEN — {cls._consecutive_failures} consecutive failures. "
                f"Will retry after {settings.MCP_CIRCUIT_BREAKER_SECONDS}s."
            )

    @classmethod
    def _record_success(cls) -> None:
        cls._consecutive_failures = 0
        cls._circuit_open_until = 0.0

    # ── Connection Management ──────────────────────────────────

    @classmethod
    async def connect(cls) -> bool:
        """
        Warm-up ping: open a short-lived SSE connection to verify the MCP
        server is reachable, then close it immediately. This is called once
        at startup to set `is_connected = True`.
        """
        logger.info("Pinging MCP SSE server to verify reachability...")
        try:
            async with AsyncExitStack() as stack:
                sse_transport = await stack.enter_async_context(
                    sse_client(
                        MCP_SSE_URL,
                        sse_read_timeout=settings.MCP_SSE_READ_TIMEOUT,
                    )
                )
                session = await stack.enter_async_context(
                    ClientSession(sse_transport[0], sse_transport[1])
                )
                await session.initialize()
                cls.is_connected = True
                cls._record_success()
                logger.info("MCP warm-up ping succeeded.")
                return True
        except Exception as e:
            logger.error(f"MCP warm-up ping failed: {e}")
            cls.is_connected = False
            cls._record_failure()
            return False

    @classmethod
    async def disconnect(cls) -> None:
        """Clean up state. No persistent connection to close."""
        cls.is_connected = False
        cls._summary_cache.clear()
        cls._structured_cache.clear()
        logger.info("MCP client state reset (disconnected).")

    # ── Per-Call Tool Execution ─────────────────────────────────

    @classmethod
    async def _call_tool(cls, tool_name: str, arguments: dict) -> Any:
        """
        Execute a single MCP tool call using a fresh SSE connection.

        Opens connection → initializes session → calls tool → closes.
        Retries with exponential backoff on transient failures.
        """
        import httpx

        last_exception = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with AsyncExitStack() as stack:
                    sse_transport = await stack.enter_async_context(
                        sse_client(
                            MCP_SSE_URL,
                            sse_read_timeout=settings.MCP_SSE_READ_TIMEOUT,
                        )
                    )
                    session = await stack.enter_async_context(
                        ClientSession(sse_transport[0], sse_transport[1])
                    )
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)

                cls._record_success()
                cls.is_connected = True
                return result

            except (httpx.RemoteProtocolError, httpx.ReadError,
                    httpx.ConnectTimeout, httpx.ReadTimeout,
                    ConnectionError, OSError, BrokenPipeError,
                    asyncio.TimeoutError) as e:
                last_exception = e
                delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))  # 1s, 2s, 4s
                logger.warning(
                    f"MCP call {tool_name} attempt {attempt}/{MAX_RETRIES} failed: "
                    f"{type(e).__name__}: {e}. Retrying in {delay:.1f}s..."
                )
                cls._record_failure()
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(delay)

            except BaseException as e:
                # The MCP SSE client wraps errors in ExceptionGroup via TaskGroup.
                # Unwrap to check if the underlying cause is a transient error.
                _transient_types = (
                    httpx.ConnectTimeout, httpx.ReadTimeout,
                    httpx.RemoteProtocolError, httpx.ReadError,
                    ConnectionError, OSError, BrokenPipeError,
                    asyncio.TimeoutError,
                )
                is_transient = False
                if isinstance(e, (ExceptionGroup, BaseExceptionGroup)):
                    is_transient = any(
                        isinstance(sub, _transient_types)
                        for sub in e.exceptions
                    )

                if is_transient:
                    last_exception = e
                    delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        f"MCP call {tool_name} attempt {attempt}/{MAX_RETRIES} failed "
                        f"(transient, wrapped in ExceptionGroup): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    cls._record_failure()
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(delay)
                else:
                    # Non-transient error (e.g. McpError from bad tool call)
                    logger.error(f"MCP tool call {tool_name} failed (non-transient): {e}")
                    cls._record_failure()
                    raise

        # All retries exhausted
        cls.is_connected = False
        logger.error(
            f"MCP call {tool_name} failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_exception}"
        )
        raise last_exception

    # ── Core Tool Calls ────────────────────────────────────────

    @classmethod
    async def list_companies(cls, owner_user_id: str) -> List[Dict[str, Any]]:
        if cls._is_circuit_open():
            logger.warning("MCP circuit breaker is OPEN. Skipping list_companies.")
            return []
        try:
            result = await cls._call_tool("list_companies", {"owner_user_id": owner_user_id})
            if result and result.content:
                text = result.content[0].text
                data = json.loads(text)
                if isinstance(data, dict) and "companies" in data:
                    return data["companies"]
                return data
            return []
        except Exception as e:
            logger.error(f"Error in list_companies: {e}")
            return []

    @classmethod
    async def get_documents(cls, company_name: str, owner_user_id: str) -> List[Dict[str, Any]]:
        if cls._is_circuit_open():
            return []
        try:
            result = await cls._call_tool(
                "retrieve_company_documents", {"company_name": company_name, "owner_user_id": owner_user_id}
            )
            if result and result.content:
                text = result.content[0].text
                data = json.loads(text)
                if isinstance(data, dict) and "documents" in data:
                    return data["documents"]
                return data
            return []
        except Exception as e:
            logger.error(f"Error in get_documents for {company_name}: {e}")
            return []

    @classmethod
    async def get_company_details(cls, company_name: str, owner_user_id: str) -> Dict[str, Any]:
        if cls._is_circuit_open():
            return {}
        try:
            result = await cls._call_tool(
                "retrieve_company_details", {"company_name": company_name, "owner_user_id": owner_user_id}
            )
            if result and result.content:
                text = result.content[0].text
                return json.loads(text)
            return {}
        except Exception as e:
            logger.error(f"Error in get_company_details for {company_name}: {e}")
            return {}

    @classmethod
    async def get_document_summaries(cls, company_name: str, owner_user_id: str) -> str:
        if cls._is_circuit_open():
            return "Document summaries are temporarily unavailable."
        try:
            result = await cls._call_tool(
                "retrieve_company_document_summaries",
                {"company_name": company_name, "owner_user_id": owner_user_id},
            )
            if result and result.content:
                return result.content[0].text
            return "No summaries returned."
        except Exception as e:
            logger.error(f"Error calling retrieve_company_document_summaries for {company_name}: {e}")
            cls._record_failure()
            return "Document summaries are temporarily unavailable."

    # ── Cached Document Summaries ──────────────────────────────

    @classmethod
    async def get_document_summaries_cached(
        cls,
        company_name: str,
        owner_user_id: str,
        ttl_seconds: int | None = None,
    ) -> str:
        """
        Fetch document summaries with TTL caching.

        During draft-all, this is called 16 times (once per section) but
        the MCP server is only hit once. Subsequent calls return cached data.

        Args:
            company_name: Company to fetch summaries for
            ttl_seconds: Cache TTL override (defaults to settings.MCP_CACHE_TTL_SECONDS)

        Returns:
            Document summaries text (raw string from MCP)
        """
        ttl = ttl_seconds or settings.MCP_CACHE_TTL_SECONDS
        cache_key = f"{owner_user_id}:{company_name.lower().strip()}"
        now = time.time()

        # Check cache
        if cache_key in cls._summary_cache:
            cached_data, cached_at = cls._summary_cache[cache_key]
            if now - cached_at < ttl:
                logger.debug(f"MCP summary cache HIT for '{company_name}'")
                return cached_data

        # Cache miss — fetch fresh
        logger.info(f"MCP summary cache MISS for '{company_name}' — fetching fresh")
        summaries = await cls.get_document_summaries(company_name, owner_user_id)

        # Only cache successful responses
        if not summaries.startswith(("Error:", "MCP")):
            cls._summary_cache[cache_key] = (summaries, now)

        return summaries

    @classmethod
    async def get_structured_data(
        cls,
        company_name: str,
        owner_user_id: str,
        rows_per_table: int = 20,
    ) -> Dict[str, Any]:
        """Fetch all available PostgreSQL credit-table data in one MCP call."""
        if cls._is_circuit_open():
            return {}
        try:
            result = await cls._call_tool(
                "retrieve_company_structured_data",
                {
                    "company_name": company_name,
                    "owner_user_id": owner_user_id,
                    "rows_per_table": rows_per_table,
                },
            )
            if result and result.content:
                data = json.loads(result.content[0].text)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(
                "Error fetching structured data for %s: %s",
                company_name,
                e,
            )
        return {}

    @classmethod
    async def get_structured_data_cached(
        cls,
        company_name: str,
        owner_user_id: str,
        ttl_seconds: int | None = None,
    ) -> Dict[str, Any]:
        """Fetch structured credit data with the same TTL as PDF summaries."""
        ttl = ttl_seconds or settings.MCP_CACHE_TTL_SECONDS
        cache_key = f"{owner_user_id}:{company_name.lower().strip()}"
        now = time.time()
        cached = cls._structured_cache.get(cache_key)
        if cached and now - cached[1] < ttl:
            return cached[0]
        data = await cls.get_structured_data(company_name, owner_user_id)
        if data.get("tables"):
            cls._structured_cache[cache_key] = (data, now)
        return data

    @classmethod
    def invalidate_cache(
        cls,
        company_name: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        """Invalidate summary cache. Pass None to clear all."""
        if company_name and owner_user_id:
            cache_key = f"{owner_user_id}:{company_name.lower().strip()}"
            cls._summary_cache.pop(cache_key, None)
            cls._structured_cache.pop(cache_key, None)
        elif company_name:
            suffix = f":{company_name.lower().strip()}"
            for cache_key in list(cls._summary_cache):
                if cache_key.endswith(suffix):
                    cls._summary_cache.pop(cache_key, None)
            for cache_key in list(cls._structured_cache):
                if cache_key.endswith(suffix):
                    cls._structured_cache.pop(cache_key, None)
        else:
            cls._summary_cache.clear()
            cls._structured_cache.clear()

    @classmethod
    def get_health_status(cls) -> Dict[str, Any]:
        """Return MCP health info for the /api/health endpoint."""
        return {
            "connected": cls.is_connected,
            "circuit_breaker_open": cls._is_circuit_open(),
            "consecutive_failures": cls._consecutive_failures,
            "cache_entries": len(cls._summary_cache),
            "structured_cache_entries": len(cls._structured_cache),
        }
