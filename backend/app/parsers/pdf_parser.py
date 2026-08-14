from __future__ import annotations

from io import BytesIO

import pdfplumber

from .common import (
    CorruptDocumentError,
    ParsedDocument,
    ScannedPdfError,
    SourceChunk,
    normalize_text,
)


def _format_table(table: list[list[object | None]]) -> str:
    lines = []
    for row in table:
        cells = [normalize_text(cell).replace("\n", " ") for cell in row]
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def parse_pdf(data: bytes) -> ParsedDocument:
    chunks: list[SourceChunk] = []
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                parts: list[str] = []
                text = normalize_text(page.extract_text() or "")
                if text:
                    parts.append(text)
                for table_number, table in enumerate(page.extract_tables() or [], start=1):
                    formatted = _format_table(table)
                    if formatted:
                        parts.append(f"[表格 {table_number}]\n{formatted}")
                content = normalize_text("\n\n".join(parts))
                if content:
                    chunks.append(
                        SourceChunk(
                            source_id=f"pdf-page-{page_number}",
                            locator=f"PDF 第 {page_number} 页",
                            content=content,
                            order=page_number,
                        )
                    )
    except Exception as exc:
        if isinstance(exc, ScannedPdfError):
            raise
        raise CorruptDocumentError("PDF 文件无法读取，可能已损坏或受密码保护。") from exc

    if not chunks:
        raise ScannedPdfError("没有从 PDF 中提取到文本；扫描版 PDF 暂不支持，请先进行 OCR。")
    return ParsedDocument(chunks=chunks, warnings=[])

