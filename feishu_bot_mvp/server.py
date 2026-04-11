#!/usr/bin/env python3
import argparse
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from counter_strategy_bank import IncomingCounterPlanner, format_counter_text
from fast_path_bank import FastReviewer


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SKILL_PATH = ROOT_DIR / "anti-laodeng"
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent / "review_schema.json"
DEFAULT_COUNTER_SCHEMA_PATH = Path(__file__).resolve().parent / "counter_schema.json"
DEFAULT_COUNTER_GUIDE_PATH = ROOT_DIR / "howtocounterlaodeng.txt"
DEFAULT_FEISHU_SDK_VENDOR_PATH = Path(__file__).resolve().parent / "_vendor"
TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
SEND_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_ts()}] {message}", flush=True)


def read_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


def read_json_object_env(name: str) -> Dict[str, str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


class Config:
    def __init__(self) -> None:
        self.host = os.environ.get("BRIDGE_HOST", "127.0.0.1")
        self.port = int(os.environ.get("BRIDGE_PORT", "8000"))
        self.feishu_app_id = os.environ.get("FEISHU_APP_ID", "").strip()
        self.feishu_app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
        self.feishu_verification_token = os.environ.get("FEISHU_VERIFICATION_TOKEN", "").strip()
        self.feishu_event_mode = os.environ.get("FEISHU_EVENT_MODE", "long_connection").strip().lower()
        self.feishu_sdk_vendor_path = Path(
            os.environ.get("FEISHU_SDK_VENDOR_PATH", str(DEFAULT_FEISHU_SDK_VENDOR_PATH))
        ).resolve()

        self.complex_reviewer_provider = os.environ.get("COMPLEX_REVIEW_PROVIDER", "openrouter").strip().lower()

        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.openrouter_model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4.1-mini").strip()
        self.openrouter_timeout_seconds = int(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "45"))
        self.openrouter_site_url = os.environ.get("OPENROUTER_SITE_URL", "").strip()
        self.openrouter_app_name = os.environ.get("OPENROUTER_APP_NAME", "feishu-anti-laodeng").strip()

        self.codex_bin = os.environ.get("CODEX_BIN", "codex").strip()
        self.codex_model = os.environ.get("CODEX_MODEL", "gpt-5.3-codex-spark").strip()
        self.codex_timeout_seconds = int(os.environ.get("CODEX_TIMEOUT_SECONDS", "90"))
        self.codex_workdir = Path(os.environ.get("CODEX_WORKDIR", str(ROOT_DIR))).resolve()

        self.compatible_chat_url = os.environ.get("COMPATIBLE_CHAT_URL", "").strip()
        self.compatible_api_key = os.environ.get("COMPATIBLE_API_KEY", "").strip()
        self.compatible_model = os.environ.get("COMPATIBLE_MODEL", "").strip()
        self.compatible_timeout_seconds = int(os.environ.get("COMPATIBLE_TIMEOUT_SECONDS", "45"))
        self.compatible_headers = read_json_object_env("COMPATIBLE_HEADERS_JSON")
        self.compatible_response_format = os.environ.get("COMPATIBLE_RESPONSE_FORMAT", "json_schema").strip().lower()

        self.fastpath_fuzzy_strict_threshold = read_float_env("FASTPATH_FUZZY_STRICT_THRESHOLD", 0.90)
        self.fastpath_fuzzy_assisted_threshold = read_float_env("FASTPATH_FUZZY_ASSISTED_THRESHOLD", 0.80)

        self.skill_path = Path(
            os.environ.get("ANTI_LAODENG_SKILL_PATH", str(DEFAULT_SKILL_PATH))
        ).resolve()
        self.schema_path = Path(
            os.environ.get("REVIEW_SCHEMA_PATH", str(DEFAULT_SCHEMA_PATH))
        ).resolve()
        self.counter_schema_path = Path(
            os.environ.get("COUNTER_SCHEMA_PATH", str(DEFAULT_COUNTER_SCHEMA_PATH))
        ).resolve()
        self.counter_guide_path = Path(
            os.environ.get("COUNTER_GUIDE_PATH", str(DEFAULT_COUNTER_GUIDE_PATH))
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
        if not self.codex_workdir.exists():
            raise ValueError(f"CODEX_WORKDIR does not exist: {self.codex_workdir}")
        if not 0.0 <= self.fastpath_fuzzy_assisted_threshold <= 1.0:
            raise ValueError("FASTPATH_FUZZY_ASSISTED_THRESHOLD must be between 0.0 and 1.0")
        if not 0.0 <= self.fastpath_fuzzy_strict_threshold <= 1.0:
            raise ValueError("FASTPATH_FUZZY_STRICT_THRESHOLD must be between 0.0 and 1.0")
        if self.fastpath_fuzzy_assisted_threshold > self.fastpath_fuzzy_strict_threshold:
            raise ValueError(
                "FASTPATH_FUZZY_ASSISTED_THRESHOLD must be less than or equal to FASTPATH_FUZZY_STRICT_THRESHOLD"
            )
        if self.compatible_response_format not in {"json_schema", "json_object", "none"}:
            raise ValueError("COMPATIBLE_RESPONSE_FORMAT must be one of: json_schema, json_object, none")

    def validate_complex_reviewer(self) -> None:
        provider = self.complex_reviewer_provider
        if provider == "openrouter":
            if not self.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is required when COMPLEX_REVIEW_PROVIDER=openrouter")
            return
        if provider == "codex":
            resolved_bin = shutil.which(self.codex_bin) if os.path.sep not in self.codex_bin else self.codex_bin
            if not resolved_bin:
                raise ValueError(f"CODEX_BIN could not be found: {self.codex_bin}")
            return
        if provider == "compatible":
            missing = []
            if not self.compatible_chat_url:
                missing.append("COMPATIBLE_CHAT_URL")
            if not self.compatible_api_key:
                missing.append("COMPATIBLE_API_KEY")
            if not self.compatible_model:
                missing.append("COMPATIBLE_MODEL")
            if missing:
                raise ValueError(
                    f"Missing required environment variables for COMPLEX_REVIEW_PROVIDER=compatible: {', '.join(missing)}"
                )
            return
        raise ValueError("COMPLEX_REVIEW_PROVIDER must be one of: openrouter, codex, compatible")

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


class StructuredReviewerBase:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.skill_context = self._load_skill_context()
        self.counter_guide = self.config.counter_guide_path.read_text(encoding="utf-8")
        self.review_schema = json.loads(self.config.schema_path.read_text(encoding="utf-8"))
        self.counter_schema = json.loads(self.config.counter_schema_path.read_text(encoding="utf-8"))

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

    def _extract_json(self, raw_content: str) -> Dict[str, Any]:
        text = raw_content.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _validate_payload(self, payload: Dict[str, Any], required: list[str], label: str) -> Dict[str, Any]:
        missing = [key for key in required if key not in payload]
        if missing:
            raise RuntimeError(f"{label} response missing keys: {', '.join(missing)}")
        return payload

    def _build_review_prompts(self, draft_text: str) -> Tuple[str, str]:
        system_prompt = (
            "You are reviewing a single outgoing workplace draft in Chinese before it is sent.\n"
            "Use the provided anti-laodeng guidance as your policy source.\n"
            "Focus on communication impact, not character judgment.\n"
            "Return JSON only. Do not wrap it in markdown."
        )
        user_prompt = (
            f"{self.skill_context}\n\n"
            "Now review this draft.\n"
            "Requirements:\n"
            "1. Infer the most likely workplace scene conservatively.\n"
            "2. Judge whether the message sounds paternalistic, condescending, vague-pressure, moralizing, or humiliating.\n"
            "3. Produce two Chinese rewrites:\n"
            "   - standard_rewrite: clear and professional\n"
            "   - firm_rewrite: firmer, but still not shaming or moralizing\n"
            "4. If the draft is already okay, still produce polished versions.\n"
            "5. Keep red_flags short and specific.\n\n"
            "Draft:\n"
            f"```text\n{draft_text}\n```"
        )
        return system_prompt, user_prompt

    def _build_counter_prompts(
        self,
        incoming_text: str,
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Tuple[str, str]:
        system_prompt = (
            "You are analyzing a workplace message that the user received from someone else.\n"
            "Your job is to suggest a low-risk counter move in Chinese.\n"
            "Do not moralize. Do not tell the user to win the argument.\n"
            "Optimize for protecting delivery, boundaries, evidence, and options.\n"
            "Return JSON only. Do not wrap it in markdown."
        )
        user_prompt = (
            "Use the following anti-laodeng outgoing guidance and incoming counter guide as policy sources.\n\n"
            f"{self.skill_context}\n\n"
            "=== INCOMING COUNTER GUIDE ===\n"
            f"{self.counter_guide}\n\n"
            "Now analyze this incoming workplace message and propose the safest counter move.\n"
            "Requirements:\n"
            "1. Infer the likely pressure type and workplace scene conservatively.\n"
            "2. Do not suggest public confrontation unless absolutely necessary.\n"
            "3. Give three reply options in Chinese: reply_soft, reply_balanced, reply_firm.\n"
            "4. Keep the replies practical and directly sendable.\n"
            "5. Include whether the user should leave evidence or escalate.\n"
            "6. Keep matched_families short and concrete.\n\n"
            f"Sender role: {sender_role}\n"
            f"Channel: {channel}\n"
            f"User preference: {user_preference}\n"
            "Incoming message:\n"
            f"```text\n{incoming_text}\n```"
        )
        return system_prompt, user_prompt


class OpenRouterReviewer(StructuredReviewerBase):
    def _complete_json(self, system_prompt: str, user_prompt: str, schema: Dict[str, Any], schema_name: str) -> Dict[str, Any]:
        payload = {
            "model": self.config.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_completion_tokens": 700,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
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
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError(f"OpenRouter returned empty content: {response_json}")
        return self._extract_json(content)

    def review(self, draft_text: str) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_review_prompts(draft_text)
        payload = self._complete_json(system_prompt, user_prompt, self.review_schema, "anti_laodeng_review")
        required = [
            "risk_level",
            "scene",
            "summary",
            "red_flags",
            "impact",
            "standard_rewrite",
            "firm_rewrite",
            "next_move",
        ]
        return self._validate_payload(payload, required, "review")

    def plan_counter(
        self,
        incoming_text: str,
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_counter_prompts(incoming_text, sender_role, channel, user_preference)
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
            "max_tokens": 700,
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

    def review(self, draft_text: str) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_review_prompts(draft_text)
        payload = self._complete_json(system_prompt, user_prompt, self.review_schema, "anti_laodeng_review")
        required = [
            "risk_level",
            "scene",
            "summary",
            "red_flags",
            "impact",
            "standard_rewrite",
            "firm_rewrite",
            "next_move",
        ]
        return self._validate_payload(payload, required, "review")

    def plan_counter(
        self,
        incoming_text: str,
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_counter_prompts(incoming_text, sender_role, channel, user_preference)
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

    def review(self, draft_text: str) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_review_prompts(draft_text)
        payload = self._complete_json(system_prompt, user_prompt, self.config.schema_path, "anti-laodeng-review")
        required = [
            "risk_level",
            "scene",
            "summary",
            "red_flags",
            "impact",
            "standard_rewrite",
            "firm_rewrite",
            "next_move",
        ]
        return self._validate_payload(payload, required, "review")

    def plan_counter(
        self,
        incoming_text: str,
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Dict[str, Any]:
        system_prompt, user_prompt = self._build_counter_prompts(incoming_text, sender_role, channel, user_preference)
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


def format_review_text(review: Dict[str, Any]) -> str:
    risk_map = {"low": "低风险", "medium": "中风险", "high": "高风险"}
    lines = [f"老登预检：{risk_map.get(review['risk_level'], review['risk_level'])}"]
    red_flags = [item.strip() for item in review.get("red_flags", []) if str(item).strip()]
    if red_flags:
        lines.extend(["", f"注意：{'；'.join(red_flags[:2])}"])
    lines.extend(
        [
            "",
            "标准版：",
            review["standard_rewrite"],
            "",
            "更坚定版：",
            review["firm_rewrite"],
        ]
    )
    next_move = str(review.get("next_move", "")).strip()
    if next_move:
        lines.extend(["", f"补一句：{next_move}"])
    return "\n".join(lines)


PREFIX_PATTERN = re.compile(r"^\s*(To|Re领导|Re同事)\s*[:：]?\s*(.*)$", re.IGNORECASE | re.DOTALL)


def parse_prefixed_request(text: str) -> Dict[str, str]:
    stripped = text.strip()
    match = PREFIX_PATTERN.match(stripped)
    if not match:
        return {
            "mode": "outgoing_review",
            "prefix": "To",
            "body": stripped,
            "sender_role": "unknown",
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
    return {
        "mode": "outgoing_review",
        "prefix": "To" if prefix == "to" else raw_prefix,
        "body": body,
        "sender_role": "unknown",
    }


def help_text() -> str:
    return (
        "给我发消息时，请用这三个前缀：\n"
        "1. `To:` 你准备发出去的话，我帮你做老登预检\n"
        "2. `Re领导:` 领导发给你的话，我帮你想低风险回复\n"
        "3. `Re同事:` 同事发给你的话，我帮你想低风险回复\n\n"
        "我会返回：\n"
        "1. 一版默认可直接发的话\n"
        "2. 一版更坚定的话\n"
        "3. 必要时的一条补充动作\n\n"
        "例子：\n"
        "- `To: 今晚必须改完，别再给我找理由。`\n"
        "- `Re领导: 别跟我解释了，今晚必须给我结果。`\n"
        "- `Re同事: 都是自己人，别老讲边界感。`\n\n"
        "目前只支持私聊里的文本消息。"
    )


def build_fast_reviewer(config: Config) -> FastReviewer:
    return FastReviewer(
        fuzzy_strict_threshold=config.fastpath_fuzzy_strict_threshold,
        fuzzy_assisted_threshold=config.fastpath_fuzzy_assisted_threshold,
    )


def build_complex_reviewer(config: Config) -> StructuredReviewerBase:
    config.validate_complex_reviewer()
    provider = config.complex_reviewer_provider
    if provider == "openrouter":
        return OpenRouterReviewer(config)
    if provider == "codex":
        return CodexReviewer(config)
    return CompatibleApiReviewer(config)


def build_counter_planner() -> IncomingCounterPlanner:
    return IncomingCounterPlanner()


class BridgeApp:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.feishu = FeishuClient(config)
        self.fast_reviewer = build_fast_reviewer(config)
        self.reviewer = build_complex_reviewer(config)
        self.counter_planner = build_counter_planner()
        self.deduper = InMemoryDeduper()
        self.queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

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
        message = (
            "这次老登预检没跑出来。\n"
            f"复杂表达当前后端：{self.config.complex_reviewer_provider}\n"
            "你可以稍后重试一次；如果持续失败，我会继续走本地模板快路径。"
        )
        try:
            self.feishu.send_text(chat_id, message)
        except Exception:
            log("failed to send failure notice:\n" + traceback.format_exc())

    def _process_message_task(self, task: Dict[str, Any]) -> None:
        text = task["text"]
        chat_id = task["chat_id"]
        message_id = task["message_id"]
        log(f"processing message {message_id} in chat {chat_id}")

        if text in {"帮助", "help", "HELP", "/help"}:
            self.feishu.send_text(chat_id, help_text())
            return

        request = parse_prefixed_request(text)
        if request["mode"] == "incoming_counter":
            sender_role = request["sender_role"]
            analysis = self.fast_reviewer.analyze(request["body"])
            if analysis:
                log(f"fast counter path hit for message {message_id}")
                plan = self.counter_planner.plan(
                    request["body"],
                    analysis,
                    sender_role=sender_role,
                )
            else:
                log(f"complex counter path provider={self.config.complex_reviewer_provider} message={message_id}")
                plan = self.reviewer.plan_counter(
                    request["body"],
                    sender_role=sender_role,
                )
            response_text = format_counter_text(plan)
        else:
            review = self.fast_reviewer.review(request["body"])
            if review:
                log(f"fast review path hit for message {message_id}")
            else:
                log(f"complex review path provider={self.config.complex_reviewer_provider} message={message_id}")
                review = self.reviewer.review(request["body"])
            response_text = format_review_text(review)
        self.feishu.send_text(chat_id, response_text)

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
                        "text": "帮助",
                    }
                )
            return
        if message_id and not self.deduper.mark_seen(message_id):
            return
        text = parse_text_content(content)
        if not chat_id or not text:
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
    if request["mode"] == "incoming_counter":
        sender_role = request["sender_role"]
        analysis = fast_reviewer.analyze(request["body"])
        if analysis:
            plan = counter_planner.plan(request["body"], analysis, sender_role=sender_role)
        else:
            reviewer = build_complex_reviewer(config)
            plan = reviewer.plan_counter(request["body"], sender_role=sender_role)
        print(format_counter_text(plan))
        return
    review = fast_reviewer.review(request["body"])
    if not review:
        reviewer = build_complex_reviewer(config)
        review = reviewer.review(request["body"])
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
