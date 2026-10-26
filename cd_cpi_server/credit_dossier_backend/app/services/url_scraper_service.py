"""Safe, bounded webpage extraction for section-specific narrative sources."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx


logger = logging.getLogger(__name__)

MAX_URLS = 10
MAX_RESPONSE_BYTES = 2_000_000
MAX_CHARS_PER_URL = 40_000
MAX_TOTAL_CHARS = 120_000
MAX_REDIRECTS = 5


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg", "canvas"}:
            self._ignored_depth += 1
        if normalized == "title":
            self._in_title = True
        if normalized in {"p", "div", "article", "section", "li", "tr", "br", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg", "canvas"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
        if normalized == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        self.parts.append(text)
        if self._in_title:
            self.title_parts.append(text)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in " ".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)

    def title(self) -> str:
        return " ".join(self.title_parts).strip()


def _public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP and HTTPS URLs are supported.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not supported.")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Local URLs are not supported.")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("The URL hostname could not be resolved.") from exc
    resolved = {item[4][0] for item in addresses}
    if not resolved or any(not _public_ip(address) for address in resolved):
        raise ValueError("Private, local, and reserved network addresses are not supported.")


async def _download(client: httpx.AsyncClient, url: str) -> tuple[str, str, str]:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await _validate_public_url(current)
        async with client.stream("GET", current, follow_redirects=False) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("The URL returned an invalid redirect.")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
                raise ValueError(f"Unsupported webpage content type: {content_type or 'unknown'}")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError("The webpage exceeds the 2 MB extraction limit.")
                chunks.append(chunk)
            encoding = response.encoding or "utf-8"
            return b"".join(chunks).decode(encoding, errors="replace"), content_type, current
    raise ValueError("The URL exceeded the redirect limit.")


async def scrape_urls(urls: list[str]) -> tuple[str, list[dict[str, object]]]:
    """Return prompt-ready webpage text and per-URL extraction details."""
    unique_urls = list(dict.fromkeys(url.strip() for url in urls if url.strip()))[:MAX_URLS]
    details: list[dict[str, object]] = []
    context_parts: list[str] = []
    total_chars = 0
    timeout = httpx.Timeout(20.0, connect=10.0)
    # Some public research sites reject explicit bot user-agents even though the
    # same article is available to a normal browser.  Send ordinary navigation
    # headers so section sources behave like links opened by the user.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        for url in unique_urls:
            try:
                raw, content_type, final_url = await _download(client, url)
                title = ""
                if "html" in content_type:
                    parser = _VisibleTextParser()
                    parser.feed(raw)
                    text = parser.text()
                    title = parser.title()
                else:
                    text = "\n".join(line.strip() for line in raw.splitlines() if line.strip())

                remaining = MAX_TOTAL_CHARS - total_chars
                text = text[: min(MAX_CHARS_PER_URL, remaining)]
                if not text:
                    raise ValueError("No readable webpage text was found.")
                total_chars += len(text)
                context_parts.append(
                    f"--- Web Source ---\nURL: {final_url}\nTitle: {title or 'Untitled'}\n"
                    f"Content:\n{text}\n--- End Web Source ---"
                )
                details.append(
                    {
                        "url": url,
                        "final_url": final_url,
                        "title": title,
                        "status": "completed",
                        "characters": len(text),
                        "error": None,
                    }
                )
                if total_chars >= MAX_TOTAL_CHARS:
                    break
            except Exception as exc:
                logger.warning("URL extraction failed for %s: %s", url, exc)
                details.append(
                    {
                        "url": url,
                        "final_url": None,
                        "title": "",
                        "status": "failed",
                        "characters": 0,
                        "error": "The URL could not be retrieved or processed.",
                    }
                )

    return "\n\n".join(context_parts), details
