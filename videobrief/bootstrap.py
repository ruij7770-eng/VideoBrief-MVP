"""Concrete composition root for the modular monolith."""

from videobrief.application.pipeline import UnderstandingPipeline
from videobrief.config import Settings
from videobrief.infrastructure.analysis.deepseek import DeepSeekAnalyzer
from videobrief.infrastructure.analysis.semantic import make_brief
from videobrief.infrastructure.sources.registry import SourceRegistry


def build_pipeline(settings: Settings | None = None) -> UnderstandingPipeline:
    settings = settings or Settings.from_env()
    analyzer_config = {
        "provider": settings.llm_provider,
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "api_key": settings.llm_api_key,
    }
    return UnderstandingPipeline(
        registry=SourceRegistry.default(),
        local_analyzer=make_brief,
        smart_analyzer=DeepSeekAnalyzer(config=analyzer_config),
    )