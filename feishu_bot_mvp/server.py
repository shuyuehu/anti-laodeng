#!/usr/bin/env python3
import argparse
import copy
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from counter_strategy_bank import IncomingCounterPlanner, format_counter_text
from fast_path_bank import FastReviewer


ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_yaml_config(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


_yaml_cfg = _load_yaml_config(ROOT_DIR / "config.yaml")


def _cfg(*keys: str, default: Any = "") -> Any:
    """Traverse nested yaml config by key path, return default if missing."""
    node = _yaml_cfg
    for k in keys:
        if isinstance(node, dict):
            node = node.get(k)
        else:
            return default
        if node is None:
            return default
    return node
DEFAULT_SKILL_PATH = ROOT_DIR / "anti-laodeng"
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent / "review_schema.json"
DEFAULT_COUNTER_SCHEMA_PATH = Path(__file__).resolve().parent / "counter_schema.json"
DEFAULT_COUNTER_GUIDE_PATH = ROOT_DIR / "howtocounterlaodeng.txt"
DEFAULT_FEISHU_SDK_VENDOR_PATH = Path(__file__).resolve().parent / "_vendor"
TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
SEND_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
SUPPORTED_COMPLEX_PROVIDERS = ("openrouter",)


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_ts()}] {message}", flush=True)


def _cfg_float(*keys: str, default: float) -> float:
    val = _cfg(*keys, default=default)
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _cfg_int(*keys: str, default: int) -> int:
    val = _cfg(*keys, default=default)
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _cfg_str(*keys: str, default: str = "") -> str:
    val = _cfg(*keys, default=default)
    return str(val).strip() if val else default


def _cfg_dict(*keys: str) -> Dict[str, str]:
    val = _cfg(*keys, default={})
    if isinstance(val, dict):
        return {str(k): str(v) for k, v in val.items()}
    return {}


def active_model_for_provider(config: "Config", provider: Optional[str] = None) -> str:
    return config.openrouter_model


class Config:
    def __init__(self) -> None:
        self.host = _cfg_str("server", "host", default="127.0.0.1")
        self.port = _cfg_int("server", "port", default=8000)
        self.feishu_app_id = _cfg_str("feishu", "app_id")
        self.feishu_app_secret = _cfg_str("feishu", "app_secret")
        self.feishu_verification_token = _cfg_str("feishu", "verification_token")
        self.feishu_event_mode = _cfg_str("feishu", "event_mode", default="long_connection").lower()
        self.feishu_sdk_vendor_path = Path(
            _cfg_str("feishu", "sdk_vendor_path") or str(DEFAULT_FEISHU_SDK_VENDOR_PATH)
        ).resolve()

        self.complex_reviewer_provider = "openrouter"

        self.openrouter_api_key = _cfg_str("backend", "api_key")
        self.openrouter_model = _cfg_str("backend", "model", default="anthropic/claude-opus-4.6")
        self.openrouter_timeout_seconds = _cfg_int("backend", "timeout_seconds", default=45)
        self.openrouter_site_url = ""
        self.openrouter_app_name = _cfg_str("backend", "app_name", default="feishu-anti-laodeng")

        self.fastpath_fuzzy_strict_threshold = _cfg_float("fastpath", "fuzzy_strict_threshold", default=0.90)
        self.fastpath_fuzzy_assisted_threshold = _cfg_float("fastpath", "fuzzy_assisted_threshold", default=0.80)

        self.skill_path = Path(
            _cfg_str("paths", "skill") or str(DEFAULT_SKILL_PATH)
        ).resolve()
        self.schema_path = Path(
            _cfg_str("paths", "review_schema") or str(DEFAULT_SCHEMA_PATH)
        ).resolve()
        self.counter_schema_path = Path(
            _cfg_str("paths", "counter_schema") or str(DEFAULT_COUNTER_SCHEMA_PATH)
        ).resolve()
        self.counter_guide_path = Path(
            _cfg_str("paths", "counter_guide") or str(DEFAULT_COUNTER_GUIDE_PATH)
        ).resolve()

    def validate_common(self) -> None:
        if self.feishu_event_mode not in {"webhook", "long_connection"}:
            raise ValueError("FEISHU_EVENT_MODE must be one of: webhook, long_connection")
        if not self.skill_path.exists():
            raise ValueError(f"Skill path does not exist: {self.skill_path}")
        if not self.schema_path.exists():
            raise ValueError(f"Schema path does not exist: {self.schema_path}")
        if not self.counter_schema_path.exists():
            raise ValueError(f"Counter schema path does not exist: {self.counter_schema_path}")
        if not self.counter_guide_path.exists():
            raise ValueError(f"Counter guide path does not exist: {self.counter_guide_path}")
        if not 0.0 <= self.fastpath_fuzzy_assisted_threshold <= 1.0:
            raise ValueError("FASTPATH_FUZZY_ASSISTED_THRESHOLD must be between 0.0 and 1.0")
        if not 0.0 <= self.fastpath_fuzzy_strict_threshold <= 1.0:
            raise ValueError("FASTPATH_FUZZY_STRICT_THRESHOLD must be between 0.0 and 1.0")
        if self.fastpath_fuzzy_assisted_threshold > self.fastpath_fuzzy_strict_threshold:
            raise ValueError(
                "FASTPATH_FUZZY_ASSISTED_THRESHOLD must be less than or equal to FASTPATH_FUZZY_STRICT_THRESHOLD"
            )

    def validate_complex_reviewer(self) -> None:
        if not self.openrouter_api_key:
            raise ValueError("backend.api_key is required in config.yaml")

    def validate_server(self) -> None:
        self.validate_common()
        missing = []
        if not self.feishu_app_id:
            missing.append("FEISHU_APP_ID")
        if not self.feishu_app_secret:
            missing.append("FEISHU_APP_SECRET")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        self.validate_complex_reviewer()


def import_feishu_sdk(config: Config):
    vendor_path = config.feishu_sdk_vendor_path
    if vendor_path.exists():
        vendor_str = str(vendor_path)
        if vendor_str not in sys.path:
            sys.path.insert(0, vendor_str)
    try:
        import lark_oapi as lark  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Feishu SDK not found. Install `lark-oapi` or set FEISHU_SDK_VENDOR_PATH to the local SDK directory."
        ) from exc
    return lark


class FeishuClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._token: Optional[str] = None
        self._token_expires_at: float = 0
        self._lock = threading.Lock()

    def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        raw = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json; charset=utf-8"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, data=raw, headers=request_headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} calling {url}: {error_body}") from exc
        return json.loads(body)

    def get_tenant_access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token

            payload = {
                "app_id": self.config.feishu_app_id,
                "app_secret": self.config.feishu_app_secret,
            }
            response = self._post_json(TENANT_TOKEN_URL, payload)
            if response.get("code") != 0:
                raise RuntimeError(f"tenant_access_token request failed: {response}")
            self._token = response["tenant_access_token"]
            self._token_expires_at = time.time() + int(response.get("expire", 7200))
            return self._token

    def send_text(self, chat_id: str, text: str) -> None:
        token = self.get_tenant_access_token()
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        response = self._post_json(
            SEND_MESSAGE_URL,
            payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.get("code") != 0:
            raise RuntimeError(f"send message failed: {response}")

    def send_post(self, chat_id: str, title: str, content: list) -> None:
        token = self.get_tenant_access_token()
        post_body = {"zh_cn": {"title": title, "content": content}}
        payload = {
            "receive_id": chat_id,
            "msg_type": "post",
            "content": json.dumps(post_body, ensure_ascii=False),
        }
        response = self._post_json(
            SEND_MESSAGE_URL,
            payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.get("code") != 0:
            raise RuntimeError(f"send post failed: {response}")


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class StructuredReviewerBase:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.skill_context = self._load_skill_context()
        self.counter_guide = self.config.counter_guide_path.read_text(encoding="utf-8")
        self.review_schema = json.loads(self.config.schema_path.read_text(encoding="utf-8"))
        self.counter_schema = json.loads(self.config.counter_schema_path.read_text(encoding="utf-8"))
        self._review_system_tpl = (PROMPTS_DIR / "review_system.txt").read_text(encoding="utf-8").strip()
        self._review_user_tpl = (PROMPTS_DIR / "review_user.txt").read_text(encoding="utf-8").strip()
        self._counter_system_tpl = (PROMPTS_DIR / "counter_system.txt").read_text(encoding="utf-8").strip()
        self._counter_user_tpl = (PROMPTS_DIR / "counter_user.txt").read_text(encoding="utf-8").strip()

    def _load_skill_context(self) -> str:
        skill_md = self.config.skill_path / "SKILL.md"
        red_flags = self.config.skill_path / "references" / "red-flags.md"
        rewrite_patterns = self.config.skill_path / "references" / "rewrite-patterns.md"
        scene_checklists = self.config.skill_path / "references" / "scene-checklists.md"
        parts = [
            "=== SKILL ===",
            skill_md.read_text(encoding="utf-8"),
            "=== RED FLAGS ===",
            red_flags.read_text(encoding="utf-8"),
            "=== REWRITE PATTERNS ===",
            rewrite_patterns.read_text(encoding="utf-8"),
            "=== SCENE CHECKLISTS ===",
            scene_checklists.read_text(encoding="utf-8"),
        ]
        return "\n".join(parts)

    @staticmethod
    def _strip_markdown_block(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            first_nl = stripped.find("\n")
            if first_nl != -1:
                stripped = stripped[first_nl + 1:]
            if stripped.rstrip().endswith("```"):
                stripped = stripped.rstrip()[:-3]
        return stripped.strip()

    @staticmethod
    def _fix_unescaped_quotes(text: str) -> str:
        result = []
        in_string = False
        i = 0
        while i < len(text):
            ch = text[i]
            if not in_string:
                result.append(ch)
                if ch == '"':
                    in_string = True
            else:
                if ch == '\\':
                    result.append(ch)
                    if i + 1 < len(text):
                        i += 1
                        result.append(text[i])
                elif ch == '"':
                    lookahead = text[i + 1:].lstrip()
                    if lookahead and lookahead[0] in (',', '}', ']', ':'):
                        result.append(ch)
                        in_string = False
                    else:
                        result.append('\\"')
                else:
                    result.append(ch)
            i += 1
        return "".join(result)

    def _extract_json(self, raw_content: str) -> Dict[str, Any]:
        text = self._strip_markdown_block(raw_content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                pass
            fixed = self._fix_unescaped_quotes(snippet)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
            fixed2 = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
            fixed2 = re.sub(r'"\s*\n\s*}', '"\n}', fixed2)
            fixed2 = re.sub(r'"\s*\n\s*]', '"\n]', fixed2)
            fixed2 = re.sub(r']\s*\n\s*"', '],\n"', fixed2)
            fixed2 = re.sub(r'}\s*\n\s*"', '},\n"', fixed2)
            try:
                return json.loads(fixed2)
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"Failed to parse JSON from LLM response: {text[:500]}")

    _FIELD_DEFAULTS: Dict[str, Any] = {
        "risk_level": "medium",
        "scene": "",
        "problem": "",
        "analysis": "",
        "follow_up": "",
    }

    def _validate_payload(self, payload: Dict[str, Any], required: list[str], label: str) -> Dict[str, Any]:
        missing = [key for key in required if key not in payload]
        for key in missing:
            if key in self._FIELD_DEFAULTS:
                payload[key] = self._FIELD_DEFAULTS[key]
                log(f"WARNING: {label} response missing '{key}', using default")
        still_missing = [key for key in required if key not in payload]
        if still_missing:
            raise RuntimeError(f"{label} response missing keys: {', '.join(still_missing)}")
        return payload

    @staticmethod
    def _build_context_block(parsed: Dict[str, str], mode: str) -> str:
        lines = []
        if parsed.get("scene"):
            lines.append(f"Scene: {parsed['scene']}")
        if parsed.get("target"):
            label = "Sender identity" if mode == "counter" else "Target recipient"
            lines.append(f"{label}: {parsed['target']}")
        if parsed.get("purpose"):
            lines.append(f"Purpose: {parsed['purpose']}")
        return "\n".join(lines)

    def _build_review_prompts(self, parsed: Dict[str, str]) -> Tuple[str, str]:
        system_prompt = self._review_system_tpl
        context_block = self._build_context_block(parsed, "review")
        user_prompt = self._review_user_tpl.format(
            skill_context=self.skill_context,
            context_block=f"Context provided by the user:\n{context_block}\n\n" if context_block else "",
            scene_hint=" (the user has provided scene context above, use it)" if parsed.get("scene") else "",
            message=parsed["message"],
        )
        return system_prompt, user_prompt

    def _build_counter_prompts(
        self,
        parsed: Dict[str, str],
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Tuple[str, str]:
        system_prompt = self._counter_system_tpl
        context_block = self._build_context_block(parsed, "counter")
        user_prompt = self._counter_user_tpl.format(
            skill_context=self.skill_context,
            counter_guide=self.counter_guide,
            context_block=f"Context provided by the user:\n{context_block}\n\n" if context_block else "",
            scene_hint=" (the user has provided context above, use it)" if context_block else "",
            sender_role=sender_role,
            channel=channel,
            user_preference=user_preference,
            message=parsed["message"],
        )
        return system_prompt, user_prompt


class OpenRouterReviewer(StructuredReviewerBase):
    def _complete_json(self, system_prompt: str, user_prompt: str, schema: Dict[str, Any], schema_name: str) -> Dict[str, Any]:
        model = self.config.openrouter_model
        is_claude = "claude" in model.lower() or "anthropic" in model.lower()
        if is_claude:
            response_format = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_completion_tokens": 8192,
            "response_format": response_format,
        }
        headers = {
            "Authorization": f"Bearer {self.config.openrouter_api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        if self.config.openrouter_site_url:
            headers["HTTP-Referer"] = self.config.openrouter_site_url
        if self.config.openrouter_app_name:
            headers["X-OpenRouter-Title"] = self.config.openrouter_app_name
        request = urllib.request.Request(
            OPENROUTER_CHAT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.openrouter_timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {error_body}") from exc

        response_json = json.loads(body)
        choices = response_json.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenRouter returned no choices: {response_json}")
        finish_reason = choices[0].get("finish_reason", "unknown")
        usage = response_json.get("usage", {})
        log(f"OpenRouter finish_reason={finish_reason} usage={usage}")
        if finish_reason == "length":
            log("WARNING: response was truncated due to max_tokens limit")
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError(f"OpenRouter returned empty content: {response_json}")
        return self._extract_json(content)

    def review(self, parsed: Dict[str, str]) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_review_prompts(parsed)
        payload = self._complete_json(system_prompt, user_prompt, self.review_schema, "anti_laodeng_review")
        required = [
            "risk_level",
            "scene",
            "problem",
            "rewrite_mild",
            "rewrite_balanced",
            "rewrite_direct",
        ]
        return self._validate_payload(payload, required, "review")

    def plan_counter(
        self,
        parsed: Dict[str, str],
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_counter_prompts(parsed, sender_role, channel, user_preference)
        payload = self._complete_json(system_prompt, user_prompt, self.counter_schema, "anti_laodeng_counter")
        required = list(self.counter_schema["required"])
        return self._validate_payload(payload, required, "counter")


class CompatibleApiReviewer(StructuredReviewerBase):
    def _complete_json(self, system_prompt: str, user_prompt: str, schema: Dict[str, Any], schema_name: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.config.compatible_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 8192,
        }
        if self.config.compatible_response_format == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
        elif self.config.compatible_response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.config.compatible_api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        headers.update(self.config.compatible_headers)
        request = urllib.request.Request(
            self.config.compatible_chat_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.compatible_timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Compatible API HTTP {exc.code}: {error_body}") from exc

        response_json = json.loads(body)
        choices = response_json.get("choices") or []
        if not choices:
            raise RuntimeError(f"Compatible API returned no choices: {response_json}")
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            text_parts = [item.get("text", "") for item in content if isinstance(item, dict)]
            content = "\n".join(part for part in text_parts if part)
        if not content:
            raise RuntimeError(f"Compatible API returned empty content: {response_json}")
        return self._extract_json(content)

    def review(self, parsed: Dict[str, str]) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_review_prompts(parsed)
        payload = self._complete_json(system_prompt, user_prompt, self.review_schema, "anti_laodeng_review")
        required = [
            "risk_level",
            "scene",
            "problem",
            "rewrite_mild",
            "rewrite_balanced",
            "rewrite_direct",
        ]
        return self._validate_payload(payload, required, "review")

    def plan_counter(
        self,
        parsed: Dict[str, str],
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_counter_prompts(parsed, sender_role, channel, user_preference)
        payload = self._complete_json(system_prompt, user_prompt, self.counter_schema, "anti_laodeng_counter")
        required = list(self.counter_schema["required"])
        return self._validate_payload(payload, required, "counter")


class CodexReviewer(StructuredReviewerBase):
    def _complete_json(self, system_prompt: str, user_prompt: str, schema_path: Path, mode_label: str) -> Dict[str, Any]:
        prompt = f"{system_prompt}\n\n{user_prompt}"
        with tempfile.NamedTemporaryFile(prefix=f"{mode_label}-", suffix=".json", delete=False) as output_file:
            output_path = Path(output_file.name)
        command = [
            self.config.codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-m",
            self.config.codex_model,
            "-C",
            str(self.config.codex_workdir),
            "-s",
            "read-only",
            prompt,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config.codex_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Codex timed out after {self.config.codex_timeout_seconds}s using model {self.config.codex_model}"
            ) from exc

        try:
            if result.returncode != 0:
                stderr = result.stderr.strip()
                stdout = result.stdout.strip()
                detail = stderr or stdout or f"exit code {result.returncode}"
                raise RuntimeError(f"Codex {mode_label} failed: {detail}")
            raw = output_path.read_text(encoding="utf-8").strip()
            if not raw:
                raise RuntimeError(f"Codex {mode_label} failed: empty final message")
            return self._extract_json(raw)
        finally:
            output_path.unlink(missing_ok=True)

    def review(self, parsed: Dict[str, str]) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_review_prompts(parsed)
        payload = self._complete_json(system_prompt, user_prompt, self.config.schema_path, "anti-laodeng-review")
        required = [
            "risk_level",
            "scene",
            "problem",
            "rewrite_mild",
            "rewrite_balanced",
            "rewrite_direct",
        ]
        return self._validate_payload(payload, required, "review")

    def plan_counter(
        self,
        parsed: Dict[str, str],
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_counter_prompts(parsed, sender_role, channel, user_preference)
        payload = self._complete_json(system_prompt, user_prompt, self.config.counter_schema_path, "anti-laodeng-counter")
        required = list(self.counter_schema["required"])
        return self._validate_payload(payload, required, "counter")


class InMemoryDeduper:
    def __init__(self, max_size: int = 500) -> None:
        self._seen = set()
        self._order = deque()
        self._max_size = max_size
        self._lock = threading.Lock()

    def mark_seen(self, item: str) -> bool:
        with self._lock:
            if item in self._seen:
                return False
            self._seen.add(item)
            self._order.append(item)
            if len(self._order) > self._max_size:
                oldest = self._order.popleft()
                self._seen.discard(oldest)
            return True


def parse_text_content(content: Any) -> str:
    if isinstance(content, dict):
        return str(content.get("text", "")).strip()
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return str(parsed.get("text", "")).strip()
        except json.JSONDecodeError:
            return content.strip()
    return ""


_EMOJI_MAP = {
    "THUMBSUP": "\U0001f44d", "OK": "\U0001f44c", "DONE": "\u2705",
    "CheckMark": "\u2705", "FIRE": "\U0001f525", "MUSCLE": "\U0001f4aa",
    "THINKING": "\U0001f914", "SMILE": "\U0001f60a", "Heart": "\u2764\ufe0f",
    "Trophy": "\U0001f3c6", "CrossMark": "\u274c", "PARTY": "\U0001f389",
    "ROCKET": "\U0001f680",
}
_EMOJI_PLACEHOLDER_RE = re.compile(r"\[:(?:EMOJI_TYPE:)?(\w+):]")
_INLINE_TOKEN_RE = re.compile(r"\*\*(.+?)\*\*")


def _replace_emoji_placeholders(text: str) -> str:
    return _EMOJI_PLACEHOLDER_RE.sub(lambda m: _EMOJI_MAP.get(m.group(1), m.group(0)), text)


def text_to_post_content(text: str) -> list:
    text = _replace_emoji_placeholders(text)
    paragraphs = []
    for line in text.split("\n"):
        if not line:
            continue
        elements = []
        last_end = 0
        for m in _INLINE_TOKEN_RE.finditer(line):
            if m.start() > last_end:
                elements.append({"tag": "text", "text": line[last_end:m.start()]})
            elements.append({"tag": "text", "text": m.group(1), "style": ["bold"]})
            last_end = m.end()
        if last_end < len(line):
            elements.append({"tag": "text", "text": line[last_end:]})
        if elements:
            paragraphs.append(elements)
    return paragraphs


def _flatten(text: str) -> str:
    joined = " ".join(line.strip() for line in text.splitlines() if line.strip())
    joined = joined.replace("**", "")
    return joined


def format_review_text(review: Dict[str, Any]) -> str:
    risk_map = {"low": "低风险", "medium": "中风险", "high": "高风险"}
    risk_emoji = {"low": "[:CheckMark:]", "medium": "[:THINKING:]", "high": "[:FIRE:]"}
    risk = review["risk_level"]
    lines = [f"**登味预检：**{risk_map.get(risk, risk)} {risk_emoji.get(risk, '')}"]
    problem = _flatten(str(review.get("problem", "")))
    if problem:
        lines.extend(["", "**登味来源：**", problem])
    lines.extend(
        [
            "",
            "**温和版改写：**",
            review["rewrite_mild"],
            "",
            "**平衡版改写：**",
            review["rewrite_balanced"],
            "",
            "**直接版改写：**",
            review["rewrite_direct"],
        ]
    )
    follow_up = _flatten(str(review.get("follow_up", "")))
    if follow_up:
        lines.extend(["", "**后续建议：**", follow_up])
    return "\n".join(lines)


_INPUT_FIELD_RE = re.compile(
    r"(?:^|\n)\s*(场景|对象|发给|回复|目的|意图)\s*[:：]\s*(.+?)(?=\n\s*(?:场景|对象|发给|回复|目的|意图)\s*[:：]|\Z)",
    re.DOTALL,
)


def parse_user_input(text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for m in _INPUT_FIELD_RE.finditer(text):
        key = m.group(1).strip()
        value = m.group(2).strip()
        if key in ("对象", "发给", "回复"):
            fields["target"] = value
        elif key == "场景":
            fields["scene"] = value
        elif key in ("目的", "意图"):
            fields["purpose"] = value
    message = _INPUT_FIELD_RE.sub("", text).strip()
    fields["message"] = message or text.strip()
    return fields


PREFIX_PATTERN = re.compile(r"^\s*(To|Re领导|Re同事|Re)\s*[:：]\s*(.*)$", re.IGNORECASE | re.DOTALL)

_LEADER_ATTR_RE = re.compile(
    r"(领导|老板|经理|主管|总监|组长|部长|boss|leader)(说|发的|发来|讲|问我|跟我说|给我发)",
    re.IGNORECASE,
)
_PEER_ATTR_RE = re.compile(
    r"(同事|他|她|对方|那个人|那人)(说|发的|发来|讲|跟我说|给我发)",
)
_IMPERATIVE_TO_USER_RE = re.compile(
    r"(你必须|你给我|你今天|你马上|你赶紧|给我一个交代|给我结果|别跟我解释|别再找理由|别给我找|今晚必须给我|不要再给我)",
)
_FIRST_PERSON_DRAFT_RE = re.compile(
    r"(我想跟|我准备发|我要发|我打算说|我想说|我准备回|我要回)",
)


def infer_message_intent(text: str) -> Dict[str, str]:
    if _LEADER_ATTR_RE.search(text):
        return {"mode": "incoming_counter", "prefix": "Re领导", "sender_role": "manager"}
    if _PEER_ATTR_RE.search(text):
        return {"mode": "incoming_counter", "prefix": "Re领导", "sender_role": "unknown"}
    if _IMPERATIVE_TO_USER_RE.search(text):
        return {"mode": "incoming_counter", "prefix": "Re领导", "sender_role": "manager"}
    if _FIRST_PERSON_DRAFT_RE.search(text):
        return {"mode": "outgoing_review", "prefix": "To", "sender_role": "unknown"}
    return {"mode": "outgoing_review", "prefix": "To", "sender_role": "unknown"}


def parse_prefixed_request(text: str) -> Dict[str, str]:
    stripped = text.strip()
    match = PREFIX_PATTERN.match(stripped)
    if not match:
        inferred = infer_message_intent(stripped)
        return {
            "mode": inferred["mode"],
            "prefix": inferred["prefix"],
            "body": stripped,
            "sender_role": inferred.get("sender_role", "unknown"),
        }
    raw_prefix = match.group(1)
    prefix = raw_prefix.lower()
    body = match.group(2).strip()
    if prefix == "re领导":
        return {
            "mode": "incoming_counter",
            "prefix": "Re领导",
            "body": body,
            "sender_role": "manager",
        }
    if prefix == "re同事":
        return {
            "mode": "incoming_counter",
            "prefix": "Re同事",
            "body": body,
            "sender_role": "peer",
        }
    if prefix == "re":
        return {
            "mode": "incoming_counter",
            "prefix": "Re",
            "body": body,
            "sender_role": "unknown",
        }
    return {
        "mode": "outgoing_review",
        "prefix": "To" if prefix == "to" else raw_prefix,
        "body": body,
        "sender_role": "unknown",
    }


def usage_text() -> str:
    return (
        'Anti老登 — 消灭职场登味，砍掉沟通内耗，让真诚成为必杀技。\n\n'
        '发消息给我就行，两种玩法：\n\n'
        '🛡 **去登味** — 发之前帮你查查有没有登味\n'
        'To：我想询问下属为什么未能按时完成需求："你这个需求很简单啊，我感觉上周就该搞定了吧？"\n'
        'To：季度复盘会后，我跟组员一对一沟通。我想鼓励他下个季度多主动承担一些："你这个季度表现还行，但说实话跟你同期进来的小王比还是差了一截。"\n\n'
        '⚔ **回登话** — 别人甩来的登味，帮你拆招\n'
        'Re领导：我最近在做个产品的新方案。我领导说"你这想法不错，但太理想化了，一看就是没被社会毒打过。你听我的，总没错。我吃过的盐比你吃过的饭多。"\n'
        'Re领导：我领导要求我们组每天加班到996，我想早点走。我领导说"趁年轻多吃点苦，对你以后有好处。现在舒服了，以后就要吃大亏。"\n'
        'Re同事：我刚加入我们公司，想找同事请教一个问题。我同事说"这个道理还要我教你？自己多悟一悟，多想想就知道了。"\n\n'
        '不加 To/Re 也行，我会自动判断。加上 Re领导/Re同事 更精准。\n\n'
        '📋 **功能按钮**\n'
        '- 使用说明 — 你正在看的这个\n'
        '- 取消 — 等不及了？随时打断\n'
        '- 查看当前模型 — 看看现在谁在帮你\n'
        '- 切换模型 — 尝试不同的模型\n'
    )


def build_fast_reviewer(config: Config) -> FastReviewer:
    return FastReviewer(
        fuzzy_strict_threshold=config.fastpath_fuzzy_strict_threshold,
        fuzzy_assisted_threshold=config.fastpath_fuzzy_assisted_threshold,
    )


def with_runtime_backend(config: Config, provider: str, model: Optional[str] = None) -> Config:
    runtime = copy.copy(config)
    runtime.complex_reviewer_provider = "openrouter"
    runtime.openrouter_model = model or runtime.openrouter_model
    return runtime


def build_complex_reviewer(config: Config) -> StructuredReviewerBase:
    config.validate_complex_reviewer()
    return OpenRouterReviewer(config)


def build_counter_planner() -> IncomingCounterPlanner:
    return IncomingCounterPlanner()


@dataclass(frozen=True)
class RuntimeBackendSelection:
    provider: str
    model: str
    source: str = "default"

    def cache_key(self) -> Tuple[str, str]:
        return (self.provider, self.model)


class BackendSettingsStore:
    def __init__(self, config: Config) -> None:
        default_provider = config.complex_reviewer_provider
        self._config = config
        self._default = RuntimeBackendSelection(
            provider=default_provider,
            model=active_model_for_provider(config, default_provider),
            source="default",
        )
        self._overrides: Dict[str, RuntimeBackendSelection] = {}
        self._lock = threading.Lock()

    def default_selection_for_provider(self, provider: str) -> RuntimeBackendSelection:
        normalized = provider.strip().lower()
        return RuntimeBackendSelection(
            provider=normalized,
            model=active_model_for_provider(self._config, normalized),
            source="custom",
        )

    def get(self, chat_id: str) -> RuntimeBackendSelection:
        with self._lock:
            return self._overrides.get(chat_id, self._default)

    def set(self, chat_id: str, provider: Optional[str] = None, model: Optional[str] = None) -> RuntimeBackendSelection:
        current = self.get(chat_id)
        next_provider = (provider or current.provider).strip().lower()
        next_model = (model or "").strip()
        if provider is not None and not next_model:
            next_model = active_model_for_provider(self._config, next_provider)
        elif not next_model:
            next_model = current.model
        selection = RuntimeBackendSelection(provider=next_provider, model=next_model, source="custom")
        with self._lock:
            self._overrides[chat_id] = selection
        return selection

    def reset(self, chat_id: str) -> RuntimeBackendSelection:
        with self._lock:
            self._overrides.pop(chat_id, None)
            return self._default


_DEFAULT_MODEL_PRESETS: Dict[str, Tuple[str, str]] = {
    "claude-opus-4.6": ("openrouter", "anthropic/claude-opus-4.6"),
    "deepseek-v3.2": ("openrouter", "deepseek/deepseek-v3.2"),
    "glm-5.1": ("openrouter", "z-ai/glm-5.1"),
    "kimi-k2.5": ("openrouter", "moonshotai/kimi-k2.5"),
}


def _load_model_presets() -> Dict[str, Tuple[str, str]]:
    raw = _cfg("model_presets", default=None)
    if not isinstance(raw, dict) or not raw:
        return dict(_DEFAULT_MODEL_PRESETS)
    return {str(k): ("openrouter", str(v)) for k, v in raw.items() if k and v}


MODEL_PRESETS: Dict[str, Tuple[str, str]] = _load_model_presets()

BACKEND_STATUS_COMMANDS = {"查看当前模型", "当前模型"}


def parse_backend_command(text: str) -> Optional[Dict[str, str]]:
    stripped = text.strip()
    if stripped in BACKEND_STATUS_COMMANDS:
        return {"action": "status"}

    switch_match = re.match(r"^\s*切换到\s*[:：]?\s*(.+?)\s*$", stripped)
    if switch_match:
        model_name = switch_match.group(1).strip()
        if not model_name:
            return {"action": "invalid", "reason": "missing_model"}
        return {"action": "switch", "model_name": model_name}
    return None


class BridgeApp:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.feishu = FeishuClient(config)
        self.fast_reviewer = build_fast_reviewer(config)
        self.counter_planner = build_counter_planner()
        self.backend_settings = BackendSettingsStore(config)
        self._reviewer_cache: Dict[Tuple[str, str], StructuredReviewerBase] = {}
        self._reviewer_cache_lock = threading.Lock()
        self._cancelled_chats: Dict[str, bool] = {}
        self._cancelled_lock = threading.Lock()
        self.deduper = InMemoryDeduper()
        self.queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def _cancel(self, chat_id: str) -> None:
        with self._cancelled_lock:
            self._cancelled_chats[chat_id] = True

    def _is_cancelled(self, chat_id: str) -> bool:
        with self._cancelled_lock:
            return self._cancelled_chats.pop(chat_id, False)

    def _worker_loop(self) -> None:
        while True:
            task = self.queue.get()
            try:
                self._process_message_task(task)
            except Exception:
                log("worker error:\n" + traceback.format_exc())
                self._send_failure_notice(task)
            finally:
                self.queue.task_done()

    def _send_failure_notice(self, task: Dict[str, Any]) -> None:
        chat_id = task.get("chat_id")
        if not chat_id:
            return
        selection = self.backend_settings.get(chat_id)
        message = (
            "这次登味预检没跑出来。\n"
            f"复杂表达当前后端：{selection.provider}\n"
            f"当前模型：{selection.model}\n"
            "你可以稍后重试一次；如果持续失败，我会继续走本地模板快路径。"
        )
        try:
            self.feishu.send_text(chat_id, message)
        except Exception:
            log("failed to send failure notice:\n" + traceback.format_exc())

    def _get_complex_reviewer(self, chat_id: str) -> Tuple[RuntimeBackendSelection, StructuredReviewerBase]:
        selection = self.backend_settings.get(chat_id)
        cache_key = selection.cache_key()
        with self._reviewer_cache_lock:
            reviewer = self._reviewer_cache.get(cache_key)
            if reviewer is not None:
                return selection, reviewer
        runtime_config = with_runtime_backend(self.config, selection.provider, selection.model)
        reviewer = build_complex_reviewer(runtime_config)
        with self._reviewer_cache_lock:
            self._reviewer_cache[cache_key] = reviewer
        return selection, reviewer

    def _format_backend_status(self, chat_id: str) -> str:
        selection = self.backend_settings.get(chat_id)
        preset_names = " / ".join(MODEL_PRESETS.keys())
        lines = [
            f"当前模型：{selection.model}",
            "",
            "可切换模型：",
        ]
        for name, (_, model_id) in MODEL_PRESETS.items():
            marker = " ← 当前" if model_id == selection.model else ""
            lines.append(f"- 切换到{name}{marker}")
        return "\n".join(lines)

    def _handle_backend_command(self, chat_id: str, text: str) -> bool:
        command = parse_backend_command(text)
        if not command:
            return False
        action = command["action"]
        if action == "status":
            self.feishu.send_text(chat_id, self._format_backend_status(chat_id))
            return True
        if action == "invalid":
            preset_names = " / ".join(MODEL_PRESETS.keys())
            self.feishu.send_text(chat_id, f"没看到模型名。可用：{preset_names}")
            return True
        if action == "switch":
            model_name = command["model_name"]
            preset = MODEL_PRESETS.get(model_name)
            if not preset:
                preset_names = " / ".join(MODEL_PRESETS.keys())
                self.feishu.send_text(
                    chat_id,
                    f"没有这个预设模型：{model_name}\n可用：{preset_names}",
                )
                return True
            provider, model_id = preset
            try:
                selection = RuntimeBackendSelection(provider=provider, model=model_id, source="custom")
                runtime_config = with_runtime_backend(self.config, selection.provider, selection.model)
                reviewer = build_complex_reviewer(runtime_config)
                with self._reviewer_cache_lock:
                    self._reviewer_cache[selection.cache_key()] = reviewer
                self.backend_settings.set(chat_id, provider=selection.provider, model=selection.model)
            except Exception as exc:
                self.feishu.send_text(chat_id, f"切换失败：{exc}")
                return True
            self.feishu.send_text(chat_id, f"已切换到 {model_name}\n模型：{model_id}")
            return True
        return False

    def _process_message_task(self, task: Dict[str, Any]) -> None:
        text = task["text"]
        chat_id = task["chat_id"]
        message_id = task["message_id"]
        log(f"processing message {message_id} in chat {chat_id}")

        self._is_cancelled(chat_id)

        used_complex = False
        request = parse_prefixed_request(text)
        parsed = parse_user_input(request["body"])
        if request["mode"] == "incoming_counter":
            sender_role = request["sender_role"]
            fast_analysis = self.fast_reviewer.analyze(parsed["message"])
            if fast_analysis:
                log(f"fast counter path would hit for message {message_id} (bypassed)")
            self.feishu.send_text(chat_id, "收到，处理中...")
            selection, reviewer = self._get_complex_reviewer(chat_id)
            log(f"complex counter path provider={selection.provider} model={selection.model} message={message_id}")
            plan = reviewer.plan_counter(
                parsed,
                sender_role=sender_role,
            )
            used_complex = True
            if used_complex and self._is_cancelled(chat_id):
                log(f"cancelled after complex counter for message {message_id}")
                return
            response_text = format_counter_text(plan)
        else:
            fast_review = self.fast_reviewer.review(parsed["message"])
            if fast_review:
                log(f"fast review path would hit for message {message_id} (bypassed)")
            self.feishu.send_text(chat_id, "收到，处理中...")
            selection, reviewer = self._get_complex_reviewer(chat_id)
            log(f"complex review path provider={selection.provider} model={selection.model} message={message_id}")
            review = reviewer.review(parsed)
            used_complex = True
            if used_complex and self._is_cancelled(chat_id):
                log(f"cancelled after complex review for message {message_id}")
                return
            response_text = format_review_text(review)
        if used_complex:
            self.feishu.send_text(chat_id, "✅ 处理成功")
        post_content = text_to_post_content(response_text)
        self.feishu.send_post(chat_id, "", post_content)

    def _accept_message_event(
        self,
        *,
        sender_type: Optional[str],
        chat_type: Optional[str],
        message_type: Optional[str],
        message_id: str,
        chat_id: str,
        content: Any,
    ) -> None:
        if sender_type and sender_type != "user":
            return
        if chat_type != "p2p":
            return
        if message_type != "text":
            if chat_id:
                self.queue.put(
                    {
                        "chat_id": chat_id,
                        "message_id": message_id or f"non-text-{time.time()}",
                        "text": "使用说明",
                    }
                )
            return
        if message_id and not self.deduper.mark_seen(message_id):
            return
        text = parse_text_content(content)
        if not chat_id or not text:
            return
        stripped = text.strip()
        if stripped in {"取消", "cancel", "CANCEL", "/cancel"}:
            self._cancel(chat_id)
            try:
                self.feishu.send_text(chat_id, "已取消当前处理。")
            except Exception:
                log("failed to send cancel notice:\n" + traceback.format_exc())
            return
        if stripped in {"使用说明", "关于", "about", "ABOUT", "/about"}:
            try:
                post_content = text_to_post_content(usage_text())
                self.feishu.send_post(chat_id, "", post_content)
            except Exception:
                log("failed to send usage text:\n" + traceback.format_exc())
            return
        if parse_backend_command(stripped):
            try:
                self._handle_backend_command(chat_id, stripped)
            except Exception:
                log("failed to handle backend command:\n" + traceback.format_exc())
            return
        self.queue.put({"chat_id": chat_id, "message_id": message_id or str(time.time()), "text": text})

    def handle_long_connection_event(self, data: Any) -> None:
        try:
            event = getattr(data, "event", None)
            if event is None:
                return
            sender = getattr(event, "sender", None)
            message = getattr(event, "message", None)
            if message is None:
                return
            self._accept_message_event(
                sender_type=getattr(sender, "sender_type", None),
                chat_type=getattr(message, "chat_type", None),
                message_type=getattr(message, "message_type", None),
                message_id=getattr(message, "message_id", "") or "",
                chat_id=getattr(message, "chat_id", "") or "",
                content=getattr(message, "content", ""),
            )
        except Exception:
            log("long connection event handling error:\n" + traceback.format_exc())

    def handle_webhook(self, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        request_type = payload.get("type")
        if request_type == "url_verification":
            if self.config.feishu_verification_token:
                token = payload.get("token", "")
                if token != self.config.feishu_verification_token:
                    return 403, {"error": "invalid verification token"}
            return 200, {"challenge": payload.get("challenge", "")}

        header = payload.get("header", {})
        event_type = header.get("event_type")
        if event_type != "im.message.receive_v1":
            return 200, {"ok": True}

        if self.config.feishu_verification_token:
            header_token = header.get("token", "")
            if header_token and header_token != self.config.feishu_verification_token:
                return 403, {"error": "invalid event token"}

        event = payload.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})
        self._accept_message_event(
            sender_type=sender.get("sender_type"),
            chat_type=message.get("chat_type"),
            message_type=message.get("message_type"),
            message_id=message.get("message_id", ""),
            chat_id=message.get("chat_id", ""),
            content=message.get("content"),
        )
        return 200, {"ok": True}


class RequestHandler(BaseHTTPRequestHandler):
    app: BridgeApp

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _write_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._write_json(200, {"ok": True})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/webhook/feishu/events":
            self._write_json(404, {"error": "not found"})
            return

        try:
            payload = self._read_json()
            status, response = self.app.handle_webhook(payload)
            self._write_json(status, response)
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid json"})
        except Exception:
            log("request error:\n" + traceback.format_exc())
            self._write_json(500, {"error": "internal server error"})

    def log_message(self, fmt: str, *args: Any) -> None:
        log(fmt % args)


def run_server(config: Config) -> None:
    config.validate_server()
    app = BridgeApp(config)
    RequestHandler.app = app
    server = ThreadingHTTPServer((config.host, config.port), RequestHandler)
    log(f"listening on http://{config.host}:{config.port}")
    server.serve_forever()


def run_long_connection(config: Config) -> None:
    config.validate_server()
    lark = import_feishu_sdk(config)
    app = BridgeApp(config)
    event_handler = (
        lark.EventDispatcherHandler.builder("", config.feishu_verification_token or "", lark.LogLevel.INFO)
        .register_p2_im_message_receive_v1(app.handle_long_connection_event)
        .build()
    )
    ws_client = lark.ws.Client(
        config.feishu_app_id,
        config.feishu_app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    log("starting Feishu long connection client")
    ws_client.start()


def review_once(config: Config, text: str) -> None:
    config.validate_common()
    fast_reviewer = build_fast_reviewer(config)
    counter_planner = build_counter_planner()
    request = parse_prefixed_request(text)
    parsed = parse_user_input(request["body"])
    reviewer = build_complex_reviewer(config)
    if request["mode"] == "incoming_counter":
        sender_role = request["sender_role"]
        plan = reviewer.plan_counter(parsed, sender_role=sender_role)
        print(format_counter_text(plan))
        return
    review = reviewer.review(parsed)
    print(format_review_text(review))


def print_fast_path_stats(config: Config) -> None:
    config.validate_common()
    reviewer = build_fast_reviewer(config)
    stats = reviewer.stats()
    print(f"family_count={stats['family_count']}")
    print(f"template_count={stats['template_count']}")
    fuzzy = stats.get("fuzzy_matching", {})
    if fuzzy:
        print(f"fuzzy_strict_threshold={fuzzy['strict_threshold']}")
        print(f"fuzzy_assisted_threshold={fuzzy['assisted_threshold']}")
    print(f"complex_reviewer_provider={config.complex_reviewer_provider}")
    for family in stats["families"]:
        print(f"{family['key']}\t{family['scene']}\t{family['templates']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Feishu anti-laodeng MVP bridge")
    parser.add_argument("--review", help="Run one local review without starting the server")
    parser.add_argument(
        "--fastpath-stats",
        action="store_true",
        help="Print local fast-path family count and template count",
    )
    parser.add_argument(
        "--fuzzy-strict-threshold",
        type=float,
        help="Override the fast-path strict fuzzy threshold for this process",
    )
    parser.add_argument(
        "--fuzzy-assisted-threshold",
        type=float,
        help="Override the fast-path assisted fuzzy threshold for this process",
    )
    parser.add_argument(
        "--event-mode",
        choices=["webhook", "long_connection"],
        help="Override Feishu event delivery mode for this process",
    )
    args = parser.parse_args()

    config = Config()
    if args.fuzzy_strict_threshold is not None:
        config.fastpath_fuzzy_strict_threshold = args.fuzzy_strict_threshold
    if args.fuzzy_assisted_threshold is not None:
        config.fastpath_fuzzy_assisted_threshold = args.fuzzy_assisted_threshold
    if args.event_mode is not None:
        config.feishu_event_mode = args.event_mode
    if args.fastpath_stats:
        print_fast_path_stats(config)
        return
    if args.review:
        review_once(config, args.review)
        return
    if config.feishu_event_mode == "webhook":
        run_server(config)
        return
    run_long_connection(config)


if __name__ == "__main__":
    main()
