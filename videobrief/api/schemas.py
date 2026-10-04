"""HTTP request DTOs; domain validation remains in AnalyseCommand."""
from pydantic import BaseModel


class AnalyseRequest(BaseModel):
    url: str = ""
    transcript: str = ""
    analysis_mode: str = "auto"
    language: str = "zh"


class QuestionRequest(BaseModel):
    question: str
