from __future__ import annotations

import csv
from io import StringIO

from charset_normalizer import from_bytes

from .common import CorruptDocumentError, EmptyDocumentError, ParsedDocument, SourceChunk, normalize_text


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def parse_csv(data: bytes) -> ParsedDocument:
    best_match = from_bytes(data).best()
    text = str(best_match) if best_match is not None else data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4_096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    try:
        rows = csv.reader(StringIO(text), dialect)
        chunks: list[SourceChunk] = []
        batch: list[str] = []
        batch_start = 1
        last_row = 0
        order = 0
        for row_number, row in enumerate(rows, start=1):
            values = [normalize_text(value).replace("\n", " ") for value in row]
            if not any(values):
                continue
            fields = [
                f"{_column_name(index)}={value}"
                for index, value in enumerate(values, start=1)
                if value
            ]
            if not batch:
                batch_start = row_number
            batch.append(f"第 {row_number} 行 | " + " | ".join(fields))
            last_row = row_number
            if len(batch) >= 30:
                order += 1
                chunks.append(
                    SourceChunk(
                        source_id=f"csv-rows-{batch_start}-{last_row}",
                        locator=f"CSV 行 {batch_start}–{last_row}",
                        content="\n".join(batch),
                        order=order,
                    )
                )
                batch = []
        if batch:
            order += 1
            chunks.append(
                SourceChunk(
                    source_id=f"csv-rows-{batch_start}-{last_row}",
                    locator=f"CSV 行 {batch_start}–{last_row}",
                    content="\n".join(batch),
                    order=order,
                )
            )
    except (csv.Error, UnicodeError) as exc:
        raise CorruptDocumentError("CSV 文件无法读取，请检查编码或分隔符。") from exc

    if not chunks:
        raise EmptyDocumentError("CSV 文件中没有可分析的数据。")
    return ParsedDocument(chunks=chunks, warnings=[])

