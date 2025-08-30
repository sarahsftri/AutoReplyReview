
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
from .constants import TOPIC_TAXONOMY

class ReviewInput(BaseModel):
    id: str
    outlet: str
    brand: str
    platform: str
    rating: Optional[int] = None
    text: str
    language: Optional[str] = None
    timestamp: Optional[str] = None
    username: Optional[str] = None
    order_type: Optional[str] = None

class ReviewAnalysis(BaseModel):
    id: str
    language: str
    sentiment: str
    topics: List[str] = Field(default_factory=list)
    severity: int
    reply_en: str
    reply_id: str

    @model_validator(mode="after")
    def _check(self):
        if self.sentiment not in {"positive","neutral","negative"}:
            raise ValueError("bad sentiment")
        if not (1 <= int(self.severity) <= 5):
            raise ValueError("bad severity")
        self.topics = [t for t in self.topics if t in TOPIC_TAXONOMY]
        if not self.topics:
            self.topics = ["service"]
        return self

class BrandVoice(BaseModel):
    tone: str = "warm, professional, concise"
    banned: List[str] = Field(default_factory=lambda: ["guarantee","free forever","100%"])
