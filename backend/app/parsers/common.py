from __future__ import annotations

import re
from dataclasses import dataclass, replace


class DocumentError(Exception):
    code = "DOCUMENT_ERROR"


class UnsupportedFileError(DocumentError):
    code = "UNSUPPORTED_FILE"


class EmptyDocumentError(DocumentError):
    code = "EMPTY_DOCUMENT"


class ScannedPdfError(DocumentError):
    code = "SCANNED_PDF"


class CorruptDocumentError(DocumentError):
    code = "CORRUPT_DOCUMENT"


@dataclass(frozen=True)
class SourceChunk:
    source_id: str
    locator: str
    content: str
    order: int


@dataclass(frozen=True)
class ParsedDocument:
    chunks: list[SourceChunk]
    warnings: list[str]


FINANCIAL_KEYWORDS = (
    "revenue",
    "income",
    "profit",
    "loss",
    "expense",
    "margin",
    "segment",
    "non-gaap",
    "adjusted",
    "reconciliation",
    "impairment",
    "liquidity",
    "cash flow",
    "tax",
    "ebitda",
    "收入",
    "营收",
    "利润",
    "亏损",
    "毛利",
    "费用",
    "分部",
    "非公认会计准则",
    "调整后",
    "调节表",
    "减值",
    "流动性",
    "现金流",
    "所得税",
)


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def relevance_score(chunk: SourceChunk) -> int:
    lowered = chunk.content.lower()
    return sum(lowered.count(keyword) for keyword in FINANCIAL_KEYWORDS)


def trim_document(document: ParsedDocument, max_chars: int) -> ParsedDocument:
    max_chars = max(8_000, min(max_chars, 300_000))
    total = sum(len(chunk.content) for chunk in document.chunks)
    if total <= max_chars:
        return document

    ranked = sorted(
        document.chunks,
        key=lambda item: (relevance_score(item), -item.order),
        reverse=True,
    )
    selected: list[SourceChunk] = []
    used = 0
    for chunk in ranked:
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(chunk.content) <= remaining:
            selected.append(chunk)
            used += len(chunk.content)
        elif not selected:
            selected.append(replace(chunk, content=chunk.content[:remaining]))
            used += remaining

    selected.sort(key=lambda item: item.order)
    warning = (
        f"文件可提取文本约 {total:,} 字符；为控制分析质量，已按财务相关性选取约 "
        f"{used:,} 字符。"
    )
    return ParsedDocument(selected, [*document.warnings, warning])

