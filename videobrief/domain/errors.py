"""Application-safe error taxonomy.

Messages are user-facing Simplified Chinese.  Infrastructure errors should be
wrapped in one of these types before they cross into the API layer.
"""
from __future__ import annotations


class VideoBriefError(Exception):
    code = "VIDEOBRIEF_ERROR"
    retryable = False

    def __init__(self, message: str, *, stage: str = "", retryable: bool | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.retryable = type(self).retryable if retryable is None else retryable

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "stage": self.stage,
        }


class InputValidationError(VideoBriefError):
    code = "INVALID_INPUT"


class UnsupportedSourceError(VideoBriefError):
    code = "UNSUPPORTED_SOURCE"


class SourceUnavailableError(VideoBriefError):
    code = "SOURCE_UNAVAILABLE"
    retryable = True


class TranscriptionError(VideoBriefError):
    code = "TRANSCRIPTION_FAILED"
    retryable = True


class AnalysisUnavailableError(VideoBriefError):
    code = "ANALYSIS_UNAVAILABLE"
    retryable = True


class BriefNotFoundError(VideoBriefError):
    code = "BRIEF_NOT_FOUND"


class JobNotFoundError(VideoBriefError):
    code = "JOB_NOT_FOUND"


class UploadTooLargeError(VideoBriefError):
    code = "UPLOAD_TOO_LARGE"


class JobCapacityError(VideoBriefError):
    code = "JOB_CAPACITY_REACHED"
    retryable = True
