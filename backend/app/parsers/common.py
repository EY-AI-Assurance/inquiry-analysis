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

TABULAR_HEADER_HINTS = (
    "项目",
    "科目",
    "指标",
    "名称",
    "期间",
    "本期",
    "上期",
    "年度",
    "季度",
    "item",
    "account",
    "description",
    "line item",
    "year ended",
    "months ended",
    "period",
    "as of",
)


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def format_tabular_row(
    row_number: int,
    values: list[str],
    headers: list[str],
    header_score: int,
) -> tuple[str, list[str], int]:
    """Render cells with human-readable headers while retaining coordinates."""
    nonempty = [value for value in values if value]
    joined = " ".join(nonempty).casefold()
    score = len(nonempty)
    if any(hint in joined for hint in TABULAR_HEADER_HINTS):
        score += 100
    if len(re.findall(r"\b(?:19|20)\d{2}\b", joined)) >= 1 and len(nonempty) >= 2:
        score += 50

    is_better_header = row_number <= 12 and score > header_score
    if is_better_header:
        headers = list(values)
        header_score = score
        fields = [
            f"{column_name(index)}列标题={value}"
            for index, value in enumerate(values, start=1)
            if value
        ]
        return (
            f"第 {row_number} 行（列标题） | " + " | ".join(fields),
            headers,
            header_score,
        )

    fields = []
    for index, value in enumerate(values, start=1):
        if not value:
            continue
        coordinate = f"{column_name(index)}{row_number}"
        header = headers[index - 1] if index <= len(headers) else ""
        label = header or f"{column_name(index)}列"
        fields.append(f"{label}（{coordinate}）={value}")
    return f"第 {row_number} 行 | " + " | ".join(fields), headers, header_score


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
