from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas import EvidenceDraft, RegulatoryBasis, ReviewDraft, ReviewQuestionDraft


def make_question(index: int) -> ReviewQuestionDraft:
    return ReviewQuestionDraft(
        question=f"问题 {index}",
        category="突出程度",
        priority="high",
        evidence=[EvidenceDraft(source_id="csv-rows-1-2", observation="文件先展示调整后指标。")],
        regulatory_basis=[RegulatoryBasis(authority="C&DI 102.10", relevance="需要同等或更突出。")],
        answer_directions=["准备版式和披露顺序对照。"],
    )


def test_review_schema_accepts_eight_to_twelve_questions():
    assert len(ReviewDraft(questions=[make_question(i) for i in range(8)]).questions) == 8
    assert len(ReviewDraft(questions=[make_question(i) for i in range(12)]).questions) == 12


def test_review_schema_rejects_too_few_questions():
    with pytest.raises(ValidationError):
        ReviewDraft(questions=[make_question(i) for i in range(7)])

