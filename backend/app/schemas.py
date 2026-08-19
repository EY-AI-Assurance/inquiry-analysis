from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SchemaModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class EvidenceDraft(SchemaModel):
    source_id: str = Field(
        alias="sourceId",
        min_length=1,
        description=(
            "必须逐字复制 document.sources[].sourceId；不得使用 location、页码描述或自创编号。"
        ),
    )
    references: list[str] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "逐字复制对应来源 content 中与事实直接相关的精确锚点；"
            "例如 Excel/CSV 单元格 A13、Word 段落 P5、Word 表格单元格 T1:R2:C3。"
            "来源没有锚点时返回空数组。"
        ),
    )
    observation: str = Field(min_length=1)


class RegulatoryBasis(SchemaModel):
    authority: str = Field(min_length=1)
    relevance: str = Field(min_length=1)


class ReviewQuestionDraft(SchemaModel):
    question: str = Field(min_length=1)
    category: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    evidence: list[EvidenceDraft] = Field(min_length=1, max_length=5)
    regulatory_basis: list[RegulatoryBasis] = Field(
        alias="regulatoryBasis", min_length=1, max_length=5
    )
    answer_directions: list[str] = Field(
        alias="answerDirections", min_length=1, max_length=6
    )


class ReviewDraft(SchemaModel):
    questions: list[ReviewQuestionDraft] = Field(min_length=8, max_length=12)


class EvidenceResponse(SchemaModel):
    source: str
    references: list[str] = Field(default_factory=list)
    observation: str


class DocumentPreviewSection(SchemaModel):
    locator: str
    content: str


class ReviewQuestionResponse(SchemaModel):
    id: str
    question: str
    category: str
    priority: Literal["high", "medium", "low"]
    evidence: list[EvidenceResponse]
    regulatory_basis: list[RegulatoryBasis] = Field(alias="regulatoryBasis")
    answer_directions: list[str] = Field(alias="answerDirections")


class AnalysisResponse(SchemaModel):
    file_name: str = Field(alias="fileName")
    review_type: Literal["SEC"] = Field(default="SEC", alias="reviewType")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="generatedAt"
    )
    warnings: list[str] = Field(default_factory=list)
    document_preview: list[DocumentPreviewSection] = Field(alias="documentPreview")
    questions: list[ReviewQuestionResponse]
