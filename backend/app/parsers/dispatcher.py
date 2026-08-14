from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from .common import (
    CorruptDocumentError,
    ParsedDocument,
    UnsupportedFileError,
    trim_document,
)
from .csv_parser import parse_csv
from .excel_parser import parse_xls, parse_xlsx
from .pdf_parser import parse_pdf
from .word_parser import parse_docx


PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".xlsx": parse_xlsx,
    ".xls": parse_xls,
    ".csv": parse_csv,
}


def _validate_office_archive(data: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            uncompressed = sum(item.file_size for item in archive.infolist())
            if uncompressed > 500 * 1024 * 1024:
                raise CorruptDocumentError("Office 文件解压后过大，无法安全处理。")
            for item in archive.infolist():
                if item.compress_size and item.file_size > 10 * 1024 * 1024:
                    if item.file_size / item.compress_size > 1_000:
                        raise CorruptDocumentError("Office 文件压缩结构异常。")
    except zipfile.BadZipFile as exc:
        raise CorruptDocumentError("Office 文件已损坏或格式不正确。") from exc


def parse_document(filename: str, data: bytes, max_chars: int = 120_000) -> ParsedDocument:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".doc":
        raise UnsupportedFileError("请将旧版 .doc 文件另存为 .docx 后重新上传。")
    parser = PARSERS.get(suffix)
    if parser is None:
        raise UnsupportedFileError("暂不支持该格式。请选择 PDF、DOCX、XLSX、XLS 或 CSV。")
    if suffix in {".docx", ".xlsx"}:
        _validate_office_archive(data)
    return trim_document(parser(data), max_chars)

