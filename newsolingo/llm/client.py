"""Unified LLM client that works with both llama.cpp and OpenRouter.

Both providers expose OpenAI-compatible endpoints, so we use the openai
Python library with different base_url configurations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from openai import OpenAI

from newsolingo.config import AppConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client wrapping the OpenAI-compatible API."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = self._create_client()
        self._model = self._get_model()

    def _create_client(self) -> OpenAI:
        """Create the appropriate OpenAI client based on provider config."""
        provider = self.config.llm.provider

        if provider == "llamacpp":
            cfg = self.config.llm.llamacpp
            return OpenAI(
                base_url=cfg.base_url,
                api_key="not-needed",
            )
        elif provider == "openrouter":
            cfg = self.config.llm.openrouter
            if not cfg.api_key or cfg.api_key.startswith("${"):
                raise ValueError(
                    "OpenRouter API key not set. Set OPENROUTER_API_KEY environment "
                    "variable or add it to your configuration file"
                )
            return OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=cfg.api_key,
            )
        elif provider == "deepseek":
            cfg = self.config.llm.deepseek
            if not cfg.api_key or cfg.api_key.startswith("${"):
                raise ValueError(
                    "DeepSeek API key not set. Set DEEPSEEK_API_KEY environment "
                    "variable or add it to your configuration file"
                )
            return OpenAI(
                base_url="https://api.deepseek.com",
                api_key=cfg.api_key,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _get_model(self) -> str:
        """Get the model name for the configured provider."""
        provider = self.config.llm.provider
        if provider == "llamacpp":
            return self.config.llm.llamacpp.model
        elif provider == "openrouter":
            return self.config.llm.openrouter.model
        elif provider == "deepseek":
            return self.config.llm.deepseek.model
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def health_check(self) -> dict[str, Any]:
        """Check if the LLM server is reachable.

        Returns a dict with keys:
            ok (bool): Whether the server is reachable.
            provider (str): The configured provider name.
            base_url (str): The base URL being used.
            model (str): The model name (from server if available).
            error (str|None): Error message if not reachable.
            context_size (int|None): Context window size (llamacpp only).

        Raises nothing - always returns a result dict.
        """
        provider = self.config.llm.provider
        if provider == "llamacpp":
            base_url = self.config.llm.llamacpp.base_url.rstrip("/v1").rstrip("/")
        elif provider == "openrouter":
            base_url = "https://openrouter.ai/api/v1"
        elif provider == "deepseek":
            base_url = "https://api.deepseek.com"
        else:
            return {
                "ok": False,
                "provider": provider,
                "base_url": "",
                "model": "",
                "error": f"Unknown provider: {provider}",
                "context_size": None,
            }

        result: dict[str, Any] = {
            "ok": False,
            "provider": provider,
            "base_url": base_url,
            "model": self._model,
            "error": None,
            "context_size": None,
        }

        try:
            if provider == "llamacpp":
                # Hit the /props endpoint for detailed server info
                resp = httpx.get(f"{base_url}/props", timeout=5.0)
                resp.raise_for_status()
                props = resp.json()
                result["ok"] = True
                result["context_size"] = props.get(
                    "default_generation_settings", {}
                ).get("n_ctx")
                # Try to get actual model name from the server
                model_alias = props.get("model_alias", "")
                if model_alias:
                    result["model"] = model_alias
            elif provider == "openrouter":
                resp = httpx.get(
                    f"{base_url}/models",
                    headers={
                        "Authorization": f"Bearer {self.config.llm.openrouter.api_key}"
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                result["ok"] = True
            elif provider == "deepseek":
                resp = httpx.get(
                    f"{base_url}/v1/models",
                    headers={
                        "Authorization": f"Bearer {self.config.llm.deepseek.api_key}"
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                result["ok"] = True
        except httpx.ConnectError:
            result["error"] = f"Cannot connect to {base_url}. Is the server running?"
        except httpx.TimeoutException:
            result["error"] = f"Connection to {base_url} timed out."
        except httpx.HTTPStatusError as e:
            result["error"] = (
                f"Server returned {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            result["error"] = str(e)

        return result

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat completion request and return the response text.

        Args:
            system_prompt: The system instruction.
            user_prompt: The user message.
            temperature: Sampling temperature (0-2).
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant's response text.
        """
        logger.debug(
            "LLM request: provider=%s, model=%s, system=%s...",
            self.config.llm.provider,
            self._model,
            system_prompt[:80],
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or ""
        logger.debug("LLM response: %s chars", len(content))
        return content

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send a chat completion and parse the response as JSON.

        The system prompt should instruct the model to respond in JSON format.
        This method extracts JSON from the response even if wrapped in markdown
        code blocks.

        Args:
            system_prompt: The system instruction (should request JSON output).
            user_prompt: The user message.
            temperature: Sampling temperature (lower for more deterministic JSON).
            max_tokens: Maximum tokens in the response.

        Returns:
            Parsed JSON as a dictionary.
        """
        raw = self.chat(system_prompt, user_prompt, temperature, max_tokens)
        return self._parse_json_response(raw)

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Extract and parse JSON from a response that might be wrapped in markdown."""
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        if "```" in text:
            # Find content between ```json (or ```) and ```
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.strip() == "```" and in_block:
                    break
                elif in_block:
                    json_lines.append(line)

            if json_lines:
                try:
                    return json.loads("\n".join(json_lines))
                except json.JSONDecodeError:
                    pass

        # Last resort: find the first { and last } and try to parse
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}...")
