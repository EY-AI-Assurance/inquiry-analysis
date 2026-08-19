from __future__ import annotations

import logging
import time
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


logger = logging.getLogger("inquiry-analysis.parser")


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
    logger.info(
        "解析器已选择 | 格式=%s | parser=%s | 文件大小=%d bytes | 字符上限=%d",
        suffix,
        parser.__name__,
        len(data),
        max_chars,
    )
    if suffix in {".docx", ".xlsx"}:
        logger.info("开始检查 Office 文件压缩结构 | 格式=%s", suffix)
        _validate_office_archive(data)
        logger.info("Office 文件压缩结构检查通过 | 格式=%s", suffix)

    parse_started_at = time.perf_counter()
    logger.info("开始提取文档内容 | parser=%s", parser.__name__)
    parsed = parser(data)
    raw_chars = sum(len(chunk.content) for chunk in parsed.chunks)
    logger.info(
        "文档内容提取完成 | 原始来源块=%d | 原始字符=%d | 耗时=%.2fs",
        len(parsed.chunks),
        raw_chars,
        time.perf_counter() - parse_started_at,
    )

    logger.info("开始检查文档长度并筛选分析内容")
    trimmed = trim_document(parsed, max_chars)
    final_chars = sum(len(chunk.content) for chunk in trimmed.chunks)
    logger.info(
        "文档解析器处理结束 | 最终来源块=%d | 最终字符=%d | 已裁剪=%s | 警告=%d",
        len(trimmed.chunks),
        final_chars,
        final_chars < raw_chars,
        len(trimmed.warnings),
    )
    return trimmed
