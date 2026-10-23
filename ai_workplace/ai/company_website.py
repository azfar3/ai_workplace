"""Fetch public company information from MicroMerger's official website."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


_BASE_URL = "https://micromerger.com"
_MAX_RESPONSE_BYTES = 1_000_000
_COMPANY_INFO_TERMS = {
    "about", "company", "what is", "who is", "who are", "tell me about", "overview",
    "micro merger", "founded", "founder", "established", "history", "since",
    "services", "service", "business", "industry", "industries", "client",
    "clients", "sector", "sectors", "office", "offices", "location",
    "address", "mission", "vision", "headquarters", "does",
}
_HR_QUERY_TERMS = {
    "policy", "leave", "salary", "payroll", "attendance", "benefit", "benefits",
    "employee", "employees", "manager", "supervisor", "onboarding", "recruitment",
    "vacancy", "vacancies", "job", "jobs", "tax", "expense", "claim", "travel",
    "medical", "insurance", "working hours", "work from home", "remote work",
}


class _PageTextParser(HTMLParser):
    """Extract readable text while ignoring navigation and executable markup."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []
        self._anchor_depth = 0
        self._anchor_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "a":
            self._anchor_depth += 1
            if self._anchor_depth == 1:
                self._anchor_parts = []
                self._anchor_href = attrs_dict.get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "a" and self._anchor_depth:
            self._anchor_depth -= 1
            if self._anchor_depth == 0:
                label = " ".join(self._anchor_parts).strip()
                href = getattr(self, "_anchor_href", "")
                if label and href:
                    self.links.append((label, href))
                self._anchor_parts = []
        if tag in {"p", "h1", "h2", "h3", "h4", "li", "br", "div"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text)
            if self._anchor_depth:
                self._anchor_parts.append(text)

    @property
    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self._parts).splitlines() if line.strip())


def is_company_information_query(query: str) -> bool:
    """Return True only for general public company profile questions."""
    normalized = " ".join((query or "").lower().replace("-", " ").split())
    if not normalized:
        return False
    if any(term in normalized for term in _HR_QUERY_TERMS):
        return False
    asks_about_company = any(term in normalized for term in ("micromerger", "micro merger", "the company", "our company"))
    asks_for_company_info = any(term in normalized for term in _COMPANY_INFO_TERMS)
    return asks_about_company and asks_for_company_info


def search_official_company_website(query: str) -> list[dict[str, Any]]:
    """Return bounded text from relevant pages on the official MicroMerger site."""
    if not is_company_information_query(query):
        return []

    cache_key = "ai_workplace:company_site_query:" + " ".join(query.lower().split())
    try:
        import frappe

        cached = frappe.cache().get_value(cache_key)
        if cached is not None:
            return cached
    except Exception:
        frappe = None

    session = requests.Session()
    headers = {"User-Agent": "MicroMerger-HR-Assistant/1.0 (+https://micromerger.com/)"}
    page_urls = [_BASE_URL + "/"]
    try:
        # Discover a relevant official page from homepage links (for example Services).
        homepage = _fetch_page(session, page_urls[0], headers)
        if homepage:
            parser = _parse_page(homepage)
            query_terms = {word for word in query.lower().split() if len(word) > 3}
            candidates = []
            for label, href in parser.links:
                absolute = urljoin(_BASE_URL + "/", href)
                parsed = urlparse(absolute)
                if parsed.scheme != "https" or parsed.hostname not in {"micromerger.com", "www.micromerger.com"}:
                    continue
                searchable = f"{label} {parsed.path}".lower()
                if any(term in searchable for term in query_terms) or any(
                    term in searchable for term in ("service", "what-we-do", "about", "industry")
                ):
                    candidates.append(absolute)
            page_urls.extend(candidates[:2])
        if len(page_urls) == 1:
            page_urls.append(_BASE_URL + "/about")

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for url in page_urls:
            if url in seen_urls or len(results) >= 3:
                continue
            seen_urls.add(url)
            html = homepage if url == page_urls[0] else _fetch_page(session, url, headers)
            if not html:
                continue
            text = _parse_page(html).text[:6000]
            if text:
                results.append({
                    "text": text,
                    "source_title": "Official MicroMerger Website",
                    "source_type": "official_website",
                    "source_url": url,
                })
        if results and frappe:
            try:
                frappe.cache().set_value(cache_key, results, expires_in_sec=3600)
            except Exception:
                pass
        return results
    except Exception as exc:
        try:
            import frappe

            frappe.logger("ai_workplace").warning(
                f"Official company website lookup failed ({type(exc).__name__}): {exc}"
            )
        except Exception:
            pass
        return []
    finally:
        session.close()


def _fetch_page(session: requests.Session, url: str, headers: dict[str, str]) -> str:
    cache_key = "ai_workplace:company_site_page:" + url
    try:
        import frappe

        cached_html = frappe.cache().get_value(cache_key)
        if cached_html is not None:
            return cached_html
    except Exception:
        frappe = None

    response = session.get(url, headers=headers, timeout=(2, 4), allow_redirects=True, stream=True)
    try:
        final_host = (urlparse(response.url).hostname or "").lower()
        if final_host not in {"micromerger.com", "www.micromerger.com"}:
            return ""
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return ""
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=16_384, decode_unicode=True):
            if not chunk:
                continue
            if isinstance(chunk, bytes):
                chunk = chunk.decode(response.encoding or "utf-8", errors="replace")
            size += len(chunk.encode("utf-8", errors="replace"))
            if size > _MAX_RESPONSE_BYTES:
                break
            chunks.append(chunk)
        html = "".join(chunks)
        if html and frappe:
            try:
                frappe.cache().set_value(cache_key, html, expires_in_sec=3600)
            except Exception:
                pass
        return html
    finally:
        response.close()


def _parse_page(html: str) -> _PageTextParser:
    parser = _PageTextParser()
    parser.feed(html)
    return parser
