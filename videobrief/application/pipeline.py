"""The single application pipeline for every supported input source."""
from __future__ import annotations

from typing import Callable

from videobrief import SCHEMA_VERSION
from videobrief.domain.models import Brief

from .commands import AnalyseCommand
from .decision import build_decision_brief
from .ports import ProgressCallback, SmartAnalyzer, SourceResolver


class UnderstandingPipeline:
    def __init__(
        self,
        registry: SourceResolver,
        local_analyzer: Callable[[list[dict]], dict],
        smart_analyzer: SmartAnalyzer,
    ) -> None:
        self._registry = registry
        self._local_analyzer = local_analyzer
        self._smart_analyzer = smart_analyzer

    @staticmethod
    def _emit(callback: ProgressCallback | None, stage: str, progress: int, message: str) -> None:
        if callback:
            callback(stage, progress, message)

    def run(self, command: AnalyseCommand, progress: ProgressCallback | None = None) -> dict:
        self._emit(progress, "acquiring", 10, "正在获取或读取内容")
        adapter = self._registry.resolve(command)
        acquisition = adapter.acquire(command, progress)

        self._emit(progress, "normalizing", 40, "正在规范化字幕和证据")
        self._emit(progress, "structuring", 55, "正在生成本地理解结构")
        result = self._local_analyzer(acquisition.rows)

        self._emit(progress, "enhancing", 72, "正在执行可选智能分析")
        result = self._smart_analyzer.enhance(acquisition.rows, result, command.analysis_mode)
        self._emit(progress, "auditing", 86, "正在核验观点与原始证据")

        # All derived first-screen fields are finalized exactly once here, after
        # optional smart enhancement. Text and upload inputs therefore cannot
        # drift into different decision summaries.
        result.update({
            "schema_version": SCHEMA_VERSION,
            "source": acquisition.source,
            "url": acquisition.url or command.url,
        })
        if acquisition.filename:
            result["filename"] = acquisition.filename
        result["decision_brief"] = build_decision_brief(result)
        self._emit(progress, "finalizing", 95, "正在完成知识页")

        return Brief.model_validate(result).model_dump(mode="json")
