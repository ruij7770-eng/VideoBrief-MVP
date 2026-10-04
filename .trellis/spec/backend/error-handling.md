# Error Handling

> Error propagation and API response conventions for VideoBrief.

---

## Error Taxonomy

Application-safe errors derive from `VideoBriefError` in `videobrief/domain/errors.py`.

Each error carries:

- a stable machine `code`;
- a Simplified Chinese user-facing `message`;
- a processing `stage`;
- a `retryable` flag.

Current categories include invalid input, unsupported source, unavailable source, transcription failure, unavailable analysis, missing Brief, missing Job, and oversized upload.

## Boundary Pattern

Infrastructure adapters catch vendor/library exceptions and raise a domain error with a safe message:

```python
try:
    ...
except VendorError as error:
    raise SourceUnavailableError(
        "视频来源暂时不可用。",
        stage="acquiring",
    ) from error
```

Keep the original exception as `__cause__` for diagnostics, but never expose its raw string when it may contain local paths, credentials, request headers, or vendor payloads.

`auto` smart analysis safely returns the deterministic result on provider failure. Explicit `smart` mode raises `AnalysisUnavailableError`; it must not silently pretend that smart analysis succeeded.

## API Envelope

Known errors preserve the historical `detail` field and add structured metadata:

```json
{
  "detail": "用户可读的简体中文错误",
  "error": {
    "code": "INVALID_INPUT",
    "message": "用户可读的简体中文错误",
    "retryable": false,
    "stage": "request"
  }
}
```

Unexpected exceptions return a generic Chinese `INTERNAL_ERROR` envelope with HTTP 500. Stack traces and internal exception text do not enter the response.

Background jobs expose the same structure under `error_info`; the legacy string `error` remains for old clients.

## HTTP Mapping

- invalid input / unsupported source: 400;
- missing Brief / Job: 404;
- upload too large: 413;
- malformed request DTO: 422;
- source / transcription / smart analysis unavailable: 502;
- unexpected internal error: 500.

## Common Mistakes

- Catching `Exception` in a route and returning vendor text.
- Returning HTTP 200 with an error-shaped body.
- Logging or returning the DeepSeek API key.
- Letting smart-mode `ValueError` bypass the API error mapper.
- Decreasing job progress when a lower-level stage reports an older value.
