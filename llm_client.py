from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class LLMClientError(RuntimeError):
    """Raised when the LLM client fails to complete a request."""



def _load_dotenv(dotenv_path: Optional[str] = None) -> None:
    """Load environment variables from a .env file.

    The function first tries python-dotenv when available. If that package is
    missing, it falls back to a tiny parser that supports KEY=VALUE lines.
    Existing environment variables are preserved.
    """
    path = Path(dotenv_path or ".env")
    if not path.exists():
        return

    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path=path, override=True)
        return
    except Exception:
        pass

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model_name: str
    timeout: int = 120

    @classmethod
    def from_env(cls, dotenv_path: Optional[str] = None) -> "LLMConfig":
        _load_dotenv(dotenv_path)

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        model_name = os.getenv("LLM_MODEL_NAME", "").strip()

        missing = [
            name
            for name, value in {
                "OPENAI_API_KEY": api_key,
                "OPENAI_BASE_URL": base_url,
                "LLM_MODEL_NAME": model_name,
            }.items()
            if not value
        ]
        if missing:
            raise LLMClientError(
                "Missing environment variables: " + ", ".join(missing)
            )

        return cls(api_key=api_key, base_url=base_url, model_name=model_name)


class OpenAICompatibleLLMClient:
    """Simple client for OpenAI-compatible chat completion APIs."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.session = requests.Session()
        self.endpoint = self._normalize_base_url(config.base_url)

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if extra_body:
            payload.update(extra_body)

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=self.config.timeout,
            )
        except requests.RequestException as exc:
            raise LLMClientError(f"HTTP request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMClientError(
                f"LLM API error {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMClientError("LLM API returned non-JSON response") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMClientError(
                f"Cannot extract message content from response: {json.dumps(data, ensure_ascii=False)[:1000]}"
            ) from exc

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        retries: int = 2,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        augmented_messages = list(messages)

        for attempt in range(retries + 1):
            try:
                content = self.chat(
                    augmented_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return self._parse_json_object(content)
            except Exception as exc:
                last_error = exc
                if attempt == retries:
                    break
                augmented_messages = list(messages) + [
                    {
                        "role": "system",
                        "content": (
                            "Your previous reply was not valid JSON. "
                            "Reply with one JSON object only, without markdown fences or extra text."
                        ),
                    }
                ]
                time.sleep(1.0)

        raise LLMClientError(f"Failed to obtain valid JSON: {last_error}")

    @staticmethod
    def _parse_json_object(text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            data = json.loads(text[start : end + 1])

        if not isinstance(data, dict):
            raise LLMClientError("Expected one JSON object from model output")
        return data


def build_client(dotenv_path: Optional[str] = None) -> OpenAICompatibleLLMClient:
    return OpenAICompatibleLLMClient(LLMConfig.from_env(dotenv_path))
