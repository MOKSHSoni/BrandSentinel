"""Web-page intake with a safe fetch: public http(s) addresses only, size and time limits, manual redirects."""

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from . import images
from .intake import IntakeError, normalise, with_image_blocks

MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 3 * 1024 * 1024
TIMEOUT = 10.0
MAX_REDIRECTS = 3
HEADERS = {"User-Agent": "BrandSentinel/1.0 (brand review; +https://github.com/MOKSHSoni/BrandSentinel)"}

BLOCK_TAGS = {"p", "div", "section", "article", "header", "footer", "main", "li", "ul", "ol", "br", "tr", "td",
              "th", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "figcaption", "aside", "nav"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe", "head"}


def check_public(url: str) -> None:
    """Refuse anything that is not a public internet address (no localhost, private ranges or metadata IPs)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise IntakeError("Enter a full web address starting with http:// or https://.")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror:
        raise IntakeError(f"Could not find {parts.hostname}.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise IntakeError("Only public web pages can be checked.")


def fetch(url: str, max_bytes: int, kinds: tuple[str, ...]) -> tuple[str, bytes, str]:
    """GET with redirects followed by hand so every hop is checked. Returns (final url, body, content type)."""
    for _ in range(MAX_REDIRECTS + 1):
        check_public(url)
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers=HEADERS) as client:
            with client.stream("GET", url) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers.get("location", ""))
                    continue
                if r.status_code >= 400:
                    raise IntakeError(f"The page returned HTTP {r.status_code}.")
                ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if not ctype.startswith(kinds):
                    raise IntakeError(f"Expected {' or '.join(kinds)}, got {ctype or 'unknown content'}.")
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        raise IntakeError("The page is too large to check.")
                return url, body, ctype
    raise IntakeError("Too many redirects.")


class _Extractor(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.title, self.parts, self.images = base, "", [""], []
        self._skip, self._in_title = 0, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "img" and not self._skip:
            src = a.get("src") or a.get("data-src")
            if src and not src.startswith("data:"):
                self.images.append((urljoin(self.base, src), a.get("alt")))  # alt None = attribute missing
        if tag in BLOCK_TAGS:
            self.parts.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in BLOCK_TAGS:
            self.parts.append("")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts[-1] += data

    def text(self) -> str:
        paras = [" ".join(p.split()) for p in self.parts]
        return "\n\n".join(p for p in paras if p)


def extract_page(url: str) -> tuple[str, list[dict], str]:
    """Returns (draft text, image assets, page title)."""
    final, body, _ = fetch(url, MAX_PAGE_BYTES, ("text/html", "application/xhtml"))
    parser = _Extractor(final)
    parser.feed(body.decode("utf-8", errors="replace"))
    assets = []
    for src, alt in parser.images:
        if len(assets) >= images.MAX_IMAGES:
            break
        try:
            _, data, _ = fetch(src, MAX_IMAGE_BYTES, ("image/",))
        except IntakeError:
            continue
        asset = images.analyse_image(data, src.rsplit("/", 1)[-1][:80] or "image", "web", alt)
        if asset.get("error") or min(asset["width"], asset["height"]) < 48:
            continue  # icons, tracking pixels and unreadable files
        assets.append(asset)
    text = normalise(with_image_blocks(parser.text(), assets), truncate=True)
    return text, assets, " ".join(parser.title.split())[:200]
