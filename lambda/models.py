from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class Span(BaseModel):
    """Model for text span information."""
    start: int
    end: int


class Citation(BaseModel):
    """Model for citation information."""
    id: str
    source: str
    content: str
    metadata: Dict[str, Any]
    span: Optional[Span] = None


class EncyclopediaRequest(BaseModel):
    """Model for encyclopedia API request."""
    prompt: str
    sessionId: Optional[str] = None


class EncyclopediaResponse(BaseModel):
    """Model for encyclopedia API response."""
    response: str
    citations: List[Citation] = []
    sessionId: Optional[str] = None