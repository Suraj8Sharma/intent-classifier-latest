from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IntentLabel(str, Enum):
    FACTUAL = "factual"
    CREATIVE_STORY = "creative_story"
    PHILOSOPHICAL = "philosophical"


class PipelineUsed(str, Enum):
    RAG = "RAG"
    CREATIVE = "Creative"
    PHILOSOPHICAL = "Philosophical"


class RetrievalStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"


class EpistemicScores(BaseModel):
    source: Optional[float] = None
    logic: Optional[float] = None
    contradiction: Optional[float] = None
    culture: Optional[float] = None


class GenerationMetadata(BaseModel):
    pipeline_used: PipelineUsed
    retrieval_status: RetrievalStatus
    trace_id: UUID
    epistemic_scores: Optional[EpistemicScores] = None
    bias_flagged: bool = False


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    query: str = Field(min_length=1)


class ChatResponse(BaseModel):
    response: str
    intent_label: IntentLabel
    metadata: GenerationMetadata
