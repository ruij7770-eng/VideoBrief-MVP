"""OpenAI-compatible DeepSeek client and two-pass smart analyzer."""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Callable

import requests

from videobrief.domain.errors import AnalysisUnavailableError

from .audit import _merge_agent_output
from .prompts import _audit_prompt, _prompt

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

def _config() -> dict:
    return {
        "provider": os.getenv("VIDEOBRIEF_LLM_PROVIDER", "deepseek"),
        "base_url": os.getenv("VIDEOBRIEF_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "model": os.getenv("VIDEOBRIEF_LLM_MODEL", DEFAULT_MODEL),
        "api_key": os.getenv("VIDEOBRIEF_LLM_API_KEY", ""),
    }


def agent_status(config: dict | None = None) -> dict:
    values = config or _config()
    return {
        "configured": bool(values["api_key"]),
        "provider": values["provider"],
        "model": values["model"],
        "base_url": values["base_url"],
    }


def _http_transport(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _parse_content(response: dict) -> dict:
    try:
        content = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise RuntimeError("智能分析服务返回结构异常。") from error
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError("智能分析没有返回有效 JSON。") from error
    if not isinstance(result, dict):
        raise RuntimeError("智能分析结果必须是 JSON 对象。")
    return result


def enhance_brief(
    rows: list[dict], brief: dict, mode: str = "auto",
    transport: Callable | None = None, config: dict | None = None,
) -> dict:
    result = deepcopy(brief)
    values = config or _config()
    if mode not in {"auto", "fast", "smart"}:
        raise ValueError("分析模式仅支持 auto、fast 或 smart。")
    if mode == "fast":
        result["agent"] = {"mode": "fast", "reason": "user_selected"}
        return result
    if not values["api_key"]:
        if mode == "smart":
            raise ValueError("智能分析尚未配置 DeepSeek API Key。")
        result["agent"] = {"mode": "fast", "reason": "missing_api_key"}
        return result

    payload = {
        "model": values["model"],
        "messages": _prompt(rows, brief),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    call = transport or _http_transport
    try:
        analysis_response = call(
            f"{values['base_url']}/chat/completions",
            {"Authorization": f"Bearer {values['api_key']}", "Content-Type": "application/json"},
            payload,
            120,
        )
        analysis = _parse_content(analysis_response)
        audit_payload = {
            "model": values["model"],
            "messages": _audit_prompt(analysis, brief),
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        audit_response = call(
            f"{values['base_url']}/chat/completions",
            {"Authorization": f"Bearer {values['api_key']}", "Content-Type": "application/json"},
            audit_payload,
            120,
        )
        audit = _parse_content(audit_response)
        return _merge_agent_output(brief, analysis, audit, values)
    except Exception as error:
        if mode == "smart":
            if isinstance(error, (ValueError, RuntimeError)):
                raise
            raise RuntimeError(f"DeepSeek 智能分析失败：{type(error).__name__}") from error
        result["agent"] = {"mode": "fast", "reason": "agent_error", "error_type": type(error).__name__}
        return result


class DeepSeekAnalyzer:
    """SmartAnalyzer adapter used by the application pipeline."""

    def __init__(self, config: dict | None = None, transport: Callable | None = None) -> None:
        self._config = config
        self._transport = transport

    def enhance(self, rows: list[dict], brief: dict, mode: str) -> dict:
        try:
            return enhance_brief(rows, brief, mode=mode, transport=self._transport, config=self._config)
        except (ValueError, RuntimeError) as error:
            raise AnalysisUnavailableError(str(error), retryable=False, stage="enhancing") from error
