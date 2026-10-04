"""Compatibility facade for VideoBrief application and infrastructure modules.

The original MVP exposed functions from this root module.  Those imports stay
stable, but all active implementations now live under the ``videobrief``
package.  New code should import from the owning module directly.
"""
from __future__ import annotations

from videobrief.application.commands import AnalyseCommand
from videobrief.application.decision import build_decision_brief
from videobrief.application.pipeline import UnderstandingPipeline
from videobrief.application.question_answering import answer_from_brief
from videobrief.bootstrap import build_pipeline
from videobrief.application.transcript import (
    parse_timestamped_transcript,
    rows_to_text,
    seconds_to_time,
    time_to_seconds,
    to_simplified,
)
from videobrief.infrastructure.analysis.semantic import make_brief
from videobrief.infrastructure.sources.compat import (
    extract_youtube_id,
    fetch_bilibili_transcript,
    fetch_youtube_transcript,
    get_whisper_model,
    source_kind,
    transcribe_local_video,
    yt_dlp_command,
)


def request_brief(
    url: str = "",
    transcript: str = "",
    model_size: str = "tiny",
    analysis_mode: str = "auto",
) -> dict:
    """Run the canonical pipeline through the historical function signature."""
    return build_pipeline().run(AnalyseCommand(
        url=url,
        transcript=transcript,
        analysis_mode=analysis_mode,
        whisper_model=model_size,
    ))


__all__ = [
    "AnalyseCommand",
    "UnderstandingPipeline",
    "answer_from_brief",
    "build_decision_brief",
    "extract_youtube_id",
    "fetch_bilibili_transcript",
    "fetch_youtube_transcript",
    "get_whisper_model",
    "make_brief",
    "parse_timestamped_transcript",
    "request_brief",
    "rows_to_text",
    "seconds_to_time",
    "source_kind",
    "time_to_seconds",
    "to_simplified",
    "transcribe_local_video",
    "yt_dlp_command",
]


if __name__ == "__main__":
    import sys

    value = sys.argv[1] if len(sys.argv) > 1 else ""
    print(request_brief(url=value) if value.startswith("http") else request_brief(transcript=value))
