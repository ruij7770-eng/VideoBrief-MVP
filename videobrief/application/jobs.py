"""Run one pipeline command and publish job progress/result snapshots."""
from __future__ import annotations

from pathlib import Path

from videobrief.domain.errors import VideoBriefError

from .commands import AnalyseCommand
from .ports import BriefRepository, JobRepository


class JobRunner:
    def __init__(self, pipeline, briefs: BriefRepository, jobs: JobRepository) -> None:
        self.pipeline = pipeline
        self.briefs = briefs
        self.jobs = jobs

    def run(self, job_id: str, command: AnalyseCommand, cleanup_path: Path | None = None) -> None:
        try:
            self.jobs.update(job_id, status="running", stage="acquiring", progress=5, message="开始处理")

            def progress(stage: str, value: int, message: str) -> None:
                self.jobs.update(job_id, status="running", stage=stage, progress=value, message=message)

            result = self.pipeline.run(command, progress)
            self.jobs.update(job_id, stage="persisting", progress=98, message="正在保存知识页")
            brief_id = self.briefs.save(result)
            result["brief_id"] = brief_id
            self.jobs.update(
                job_id, status="completed", stage="completed", progress=100,
                message="知识页已生成", result=result, error=None, error_info=None,
            )
        except VideoBriefError as error:
            self.jobs.update(
                job_id, status="failed", stage=error.stage or "failed", progress=100,
                message="处理失败", error=error.message,
                error_info=error.to_dict(),
            )
        except Exception as error:
            self.jobs.update(
                job_id, status="failed", stage="failed", progress=100,
                message="处理失败", error="处理过程中发生内部错误。",
                error_info={"code": "INTERNAL_ERROR", "message": "处理过程中发生内部错误。", "retryable": False, "stage": "failed"},
            )
        finally:
            if cleanup_path:
                Path(cleanup_path).unlink(missing_ok=True)
