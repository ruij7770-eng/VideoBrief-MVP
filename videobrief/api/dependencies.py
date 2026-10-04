"""Composition container; the only place concrete adapters are wired."""
from __future__ import annotations

from dataclasses import dataclass, field

from videobrief.application.jobs import JobRunner
from videobrief.application.pipeline import UnderstandingPipeline
from videobrief.bootstrap import build_pipeline
from videobrief.config import Settings
from videobrief.infrastructure.jobs.memory import InMemoryJobRepository
from videobrief.infrastructure.persistence.sqlite import SQLiteBriefRepository


@dataclass
class ApplicationContainer:
    settings: Settings
    briefs: SQLiteBriefRepository
    jobs: InMemoryJobRepository
    pipeline: UnderstandingPipeline
    runner: JobRunner = field(init=False)

    def __post_init__(self) -> None:
        self.runner = JobRunner(self.pipeline, self.briefs, self.jobs)

    @classmethod
    def default(cls) -> "ApplicationContainer":
        settings = Settings.from_env()
        return cls(
            settings=settings,
            briefs=SQLiteBriefRepository(settings.db_path),
            jobs=InMemoryJobRepository(),
            pipeline=build_pipeline(),
        )
