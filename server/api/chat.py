import uuid

from fastapi import APIRouter

from schemas.models import (
    ChatRequest,
    ChatResponse,
    GenerationMetadata,
    IntentLabel,
    PipelineUsed,
    RetrievalStatus,
)

router = APIRouter()


def _fallback_response() -> ChatResponse:
    """Malformed classifier/generator output: no retry, fall through to a standard factual RAG response (spec §5)."""
    return ChatResponse(
        response="I'm experiencing a temporary processing issue.",
        intent_label=IntentLabel.FACTUAL,
        metadata=GenerationMetadata(
            pipeline_used=PipelineUsed.RAG,
            retrieval_status=RetrievalStatus.OK,
            trace_id=uuid.uuid4(),
        ),
    )


def _run_pipeline(request: ChatRequest) -> ChatResponse:
    """Chunk 1 stub: real classification/retrieval/generation land in a later chunk."""
    return ChatResponse(
        response=f"Echo: {request.query}",
        intent_label=IntentLabel.FACTUAL,
        metadata=GenerationMetadata(
            pipeline_used=PipelineUsed.RAG,
            retrieval_status=RetrievalStatus.OK,
            trace_id=uuid.uuid4(),
        ),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return _run_pipeline(request)
