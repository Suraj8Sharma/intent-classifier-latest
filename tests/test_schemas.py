from uuid import uuid4

import pytest
from pydantic import ValidationError

from schemas.models import (
    ChatRequest,
    ChatResponse,
    GenerationMetadata,
    IntentLabel,
    PipelineUsed,
    RetrievalStatus,
)


def test_chat_request_rejects_invalid_uuid():
    with pytest.raises(ValidationError):
        ChatRequest(user_id="not-a-uuid", query="hi")


def test_chat_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ChatRequest(user_id=uuid4(), query="hi", extra_field="nope")


def test_chat_request_rejects_empty_query():
    with pytest.raises(ValidationError):
        ChatRequest(user_id=uuid4(), query="")


def test_chat_request_accepts_valid_payload():
    request = ChatRequest(user_id=uuid4(), query="hello")
    assert request.query == "hello"


def test_chat_response_serializes_null_metadata_fields():
    response = ChatResponse(
        response="hello",
        intent_label=IntentLabel.FACTUAL,
        metadata=GenerationMetadata(
            pipeline_used=PipelineUsed.RAG,
            retrieval_status=RetrievalStatus.OK,
            trace_id=uuid4(),
        ),
    )
    dumped = response.model_dump()
    assert dumped["metadata"]["epistemic_scores"] is None
    assert dumped["metadata"]["bias_flagged"] is False
