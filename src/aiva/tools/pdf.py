"""PDF skills powered by PyMuPDF: create (from markdown), read, merge, split, rotate, watermark.

PDFs are written to ``<workspace>/pdfs`` and opened in Preview, which makes a nice
demo moment ("AIVA, make a PDF of today's notes").
"""

from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime
from pathlib import Path

import pymupdf
from pydantic_ai import RunContext

from ..brain.deps import AgentDeps
from ..brain.toolsets import ToolRegistry
from .files import resolve_path
from .system import open_target

_CSS = """
body { font-family: sans-serif; font-size: 11.5pt; line-height: 1.45; color: #1f2937; }
h1 { font-size: 22pt; color: #4338ca; margin-bottom: 4pt; }
h2 { font-size: 15pt; color: #3730a3; margin-top: 14pt; }
h3 { font-size: 12.5pt; color: #312e81; margin-top: 10pt; }
.meta { color: #6b7280; font-size: 9pt; margin-bottom: 14pt; }
li { margin-bottom: 3pt; }
hr { border: 0; border-top: 1px solid #c7d2fe; }
code { font-family: monospace; background: #eef2ff; }
"""


def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def markdown_to_html(markdown: str) -> str:
    """Tiny markdown subset → HTML: #/##/### headings, -/* and 1. lists, ---, **bold**, *italic*."""
    out: list[str] = []
    list_tag: str | None = None
    paragraph: list[str] = []

    def close_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            close_paragraph()
            close_list()
            continue
        if m := re.match(r"^(#{1,3})\s+(.*)", line):
            close_paragraph()
            close_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
        elif re.match(r"^(-{3,}|\*{3,})$", line):
            close_paragraph()
            close_list()
            out.append("<hr/>")
        elif m := re.match(r"^[-*•]\s+(.*)", line):
            close_paragraph()
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append(f"<li>{_inline(m.group(1))}</li>")
        elif m := re.match(r"^\d+[.)]\s+(.*)", line):
            close_paragraph()
            if list_tag != "ol":
                close_list()
                out.append("<ol>")
                list_tag = "ol"
            out.append(f"<li>{_inline(m.group(1))}</li>")
        else:
            close_list()
            paragraph.append(line)
    close_paragraph()
    close_list()
    return "\n".join(out)


def write_pdf(path: Path, title: str, markdown: str) -> int:
    """Render title + markdown to a multi-page A4 PDF. Returns the page count."""
    body = f"<h1>{html.escape(title)}</h1><p class='meta'>Created by AIVA · {datetime.now():%d %b %Y, %I:%M %p}</p>"
    body += markdown_to_html(markdown)
    story = pymupdf.Story(html=body, user_css=_CSS)
    writer = pymupdf.DocumentWriter(str(path))
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (54, 54, -54, -54)  # noqa: RUF005 - pymupdf Rect arithmetic
    pages, more = 0, True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
        pages += 1
    writer.close()
    return pages


def _parse_pages(spec: str, count: int) -> list[int]:
    """'1-3,5' (1-based, inclusive) → [0, 1, 2, 4]."""
    pages: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a or 1), int(b or count)
            pages.extend(range(start - 1, min(end, count)))
        else:
            pages.append(int(part) - 1)
    return [p for p in pages if 0 <= p < count]


def _out_dir(ctx: RunContext[AgentDeps]) -> Path:
    folder = ctx.deps.services.config.workspace_path / "pdfs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _slug(text: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", text.strip().lower(), flags=re.ASCII).strip("-")
    return slug[:40] or "document"


def _find_pdf(ctx: RunContext[AgentDeps], name: str) -> Path | None:
    path = resolve_path(ctx, name)
    if path is None and not name.lower().endswith(".pdf"):
        path = resolve_path(ctx, name + ".pdf")
    return path if path and path.suffix.lower() == ".pdf" else None


def register(reg: ToolRegistry) -> None:
    @reg.tool("pdf")
    async def create_pdf(
        ctx: RunContext[AgentDeps], title: str, content: str, filename: str = "", open_after: bool = True
    ) -> str:
        """Create a nicely formatted PDF (notes, report, letter, resume…) and open it.

        Args:
            title: Document title.
            content: Body in simple markdown: # headings, - bullets, 1. lists, **bold**. Hindi is supported.
            filename: Optional file name without extension.
            open_after: Open in Preview when done.
        """
        path = _out_dir(ctx) / f"{_slug(filename or title)}-{datetime.now():%Y%m%d-%H%M%S}.pdf"
        try:
            pages = await asyncio.to_thread(write_pdf, path, title, content)
        except Exception as exc:
            return f"PDF creation failed: {exc}"
        if open_after:
            await open_target(str(path))
        return f"Created {path.name} ({pages} page{'s' if pages != 1 else ''}) in the AIVA/pdfs folder."

    @reg.tool("pdf")
    def read_pdf(ctx: RunContext[AgentDeps], name: str, pages: str = "") -> str:
        """Read the text of a PDF (to summarise or answer questions about it).

        Args:
            name: PDF file name (or part of it) in workspace/Downloads/Documents/Desktop.
            pages: Optional page range like "1-2". Empty = from the start.
        """
        path = _find_pdf(ctx, name)
        if path is None:
            return f"Couldn't find a PDF matching '{name}'."
        with pymupdf.open(path) as doc:
            selected = _parse_pages(pages, doc.page_count) if pages else list(range(doc.page_count))
            text = "\n".join(doc[i].get_text() for i in selected[:30])
            count = doc.page_count
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return f"{path.name} — {count} pages.\n" + (
            text[:3500] + (" …" if len(text) > 3500 else "") or "(no text layer)"
        )

    @reg.tool("pdf")
    async def merge_pdfs(ctx: RunContext[AgentDeps], names: list[str], output_name: str = "merged") -> str:
        """Combine several PDFs into one, in the given order.

        Args:
            names: PDF names (or parts of names), in order.
            output_name: Name for the merged file.
        """
        paths = []
        for name in names:
            path = _find_pdf(ctx, name)
            if path is None:
                return f"Couldn't find a PDF matching '{name}'."
            paths.append(path)
        out = _out_dir(ctx) / f"{_slug(output_name)}-{datetime.now():%H%M%S}.pdf"
        with pymupdf.open() as merged:
            for path in paths:
                with pymupdf.open(path) as src:
                    merged.insert_pdf(src)
            merged.save(out)
            total = merged.page_count
        await open_target(str(out))
        return f"Merged {len(paths)} PDFs into {out.name} ({total} pages)."

    @reg.tool("pdf")
    async def extract_pages(ctx: RunContext[AgentDeps], name: str, pages: str, output_name: str = "") -> str:
        """Save selected pages of a PDF as a new PDF (split).

        Args:
            name: Source PDF.
            pages: Page range like "1-3,5".
            output_name: Optional name for the new file.
        """
        path = _find_pdf(ctx, name)
        if path is None:
            return f"Couldn't find a PDF matching '{name}'."
        with pymupdf.open(path) as doc:
            selected = _parse_pages(pages, doc.page_count)
            if not selected:
                return f"No valid pages in '{pages}' (the PDF has {doc.page_count})."
            doc.select(selected)
            out = _out_dir(ctx) / f"{_slug(output_name or path.stem + '-pages')}-{datetime.now():%H%M%S}.pdf"
            doc.save(out)
        await open_target(str(out))
        return f"Saved pages {pages} as {out.name}."

    @reg.tool("pdf")
    def rotate_pdf(ctx: RunContext[AgentDeps], name: str, degrees: int = 90, pages: str = "") -> str:
        """Rotate pages of a PDF (saved as a new file).

        Args:
            name: Source PDF.
            degrees: 90, 180 or 270.
            pages: Optional page range; empty = all pages.
        """
        path = _find_pdf(ctx, name)
        if path is None:
            return f"Couldn't find a PDF matching '{name}'."
        with pymupdf.open(path) as doc:
            for i in _parse_pages(pages, doc.page_count) if pages else range(doc.page_count):
                doc[i].set_rotation((doc[i].rotation + degrees) % 360)
            out = _out_dir(ctx) / f"{_slug(path.stem)}-rotated-{datetime.now():%H%M%S}.pdf"
            doc.save(out)
        return f"Saved rotated copy as {out.name}."

    @reg.tool("pdf")
    def add_watermark(ctx: RunContext[AgentDeps], name: str, text: str) -> str:
        """Stamp a diagonal text watermark (e.g. CONFIDENTIAL, DRAFT) on every page.

        Args:
            name: Source PDF.
            text: Watermark text.
        """
        path = _find_pdf(ctx, name)
        if path is None:
            return f"Couldn't find a PDF matching '{name}'."
        with pymupdf.open(path) as doc:
            for page in doc:
                rect = page.rect
                size = max(24, min(rect.width, rect.height) / max(6, len(text)) * 1.6)
                page.insert_text(
                    pymupdf.Point(rect.width * 0.18, rect.height * 0.62),
                    text,
                    fontsize=size,
                    color=(0.55, 0.55, 0.75),
                    fill_opacity=0.25,
                    morph=(pymupdf.Point(rect.width / 2, rect.height / 2), pymupdf.Matrix(-35)),
                    overlay=True,
                )
            out = _out_dir(ctx) / f"{_slug(path.stem)}-watermarked-{datetime.now():%H%M%S}.pdf"
            doc.save(out)
        return f"Saved watermarked copy as {out.name}."
