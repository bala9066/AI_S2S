"""
Base Agent class with Claude API tool_use and LLM fallback chain.

Fallback order:
  1. Claude Opus 4.6   (primary - complex reasoning)
  2. Claude Haiku 4.5  (same API, cheaper tokens)
  3. Ollama local       (air-gapped, no token limits)
  4. GLM-4             (last resort)
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

import anthropic
import httpx
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for all pipeline phase agents.

    Each agent has:
    - A system prompt with domain expertise
    - Access to specific tools (Claude tool_use format)
    - Fallback chain for token limits / rate limits
    - Structured input/output
    """

    def __init__(
        self,
        phase_number: str,
        phase_name: str,
        model: Optional[str] = None,
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        max_tokens: int = 16384,
    ):
        self.phase_number = phase_number
        self.phase_name = phase_name
        self.model = model or settings.primary_model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.max_tokens = max_tokens

        # Initialize Anthropic client (Claude API)
        self._anthropic_client: Optional[anthropic.Anthropic] = None
        if settings.anthropic_api_key:
            self._anthropic_client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key
            )

        # Initialize DeepSeek client (OpenAI-compatible API)
        self._deepseek_client: Optional[AsyncOpenAI] = None
        if settings.deepseek_api_key:
            self._deepseek_client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
            logger.info("DeepSeek client initialized — using DeepSeek-V3 as primary LLM")

        # Fallback chain — auto-promote based on available keys
        self.fallback_chain = settings.fallback_chain
        if not settings.anthropic_api_key and not settings.deepseek_api_key and settings.glm_api_key:
            logger.info("No Anthropic/DeepSeek key — using GLM via Z.AI as primary LLM")

    @abstractmethod
    async def execute(self, project_context: dict, user_input: str) -> dict:
        """
        Execute this agent's phase.

        Args:
            project_context: Current project state and outputs from prior phases.
            user_input: User's message or requirements text.

        Returns:
            dict with phase outputs (files generated, data extracted, etc.)
        """
        pass

    @abstractmethod
    def get_system_prompt(self, project_context: dict) -> str:
        """Build the system prompt with project-specific context."""
        pass

    async def call_llm(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        model: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """
        Call Claude API with automatic fallback chain.

        Returns:
            dict with 'content' (text), 'tool_calls' (if any), 'model_used', 'stop_reason'
        """
        model = model or self.model
        system = system or self.system_prompt
        tools = tools or self.tools
        max_tokens = max_tokens or self.max_tokens

        # Try each model in the fallback chain
        chain = [model] + [m for m in self.fallback_chain if m != model]

        last_error = None
        for fallback_model in chain:
            try:
                result = await self._call_model(
                    fallback_model, messages, system, tools, max_tokens
                )
                if result:
                    result["model_used"] = fallback_model
                    usage = result.get("usage", {})
                    logger.info(
                        "llm.call_ok phase=%s model=%s in=%s out=%s",
                        self.phase_number, fallback_model,
                        usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                        extra={"phase": self.phase_number, "model": fallback_model},
                    )
                    return result
            except anthropic.RateLimitError as e:
                logger.warning(
                    "llm.rate_limit phase=%s model=%s — trying next",
                    self.phase_number, fallback_model,
                    extra={"phase": self.phase_number},
                )
                last_error = e
            except anthropic.APIStatusError as e:
                if "token" in str(e).lower() or "limit" in str(e).lower():
                    logger.warning(
                        "llm.token_limit phase=%s model=%s — trying next",
                        self.phase_number, fallback_model,
                        extra={"phase": self.phase_number},
                    )
                    last_error = e
                else:
                    raise
            except Exception as e:
                logger.warning(
                    "llm.error phase=%s model=%s: %s — trying next",
                    self.phase_number, fallback_model, e,
                    extra={"phase": self.phase_number},
                )
                last_error = e

        raise RuntimeError(
            f"All models in fallback chain failed. Last error: {last_error}"
        )

    async def _call_model(
        self,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int,
    ) -> Optional[dict]:
        """Route to the correct API based on model name."""

        if model.startswith("claude"):
            return await self._call_anthropic(model, messages, system, tools, max_tokens)
        elif model.startswith("deepseek"):
            return await self._call_deepseek(model, messages, system, tools, max_tokens)
        elif model.startswith("ollama"):
            return await self._call_ollama(model, messages, system, max_tokens)
        elif model.startswith("glm"):
            # GLM via Z.AI uses Anthropic-compatible API — full tool_use support
            return await self._call_glm_anthropic(model, messages, system, tools, max_tokens)
        else:
            logger.warning(f"Unknown model type: {model}")
            return None

    async def _call_anthropic(
        self,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int,
    ) -> dict:
        """Call Claude API with native tool_use."""
        if not self._anthropic_client:
            raise RuntimeError("Anthropic client not initialized (missing API key)")

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = self._anthropic_client.messages.create(**kwargs)

        # Parse response
        content_text = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }

    async def _call_deepseek(
        self,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int,
    ) -> dict:
        """Call DeepSeek API (OpenAI-compatible).

        DeepSeek-V3 ('deepseek-chat') supports function/tool calling via the
        OpenAI tools schema.  Tool definitions are converted from Anthropic
        format → OpenAI format on the fly.
        """
        if not self._deepseek_client:
            raise RuntimeError("DeepSeek client not initialized (missing DEEPSEEK_API_KEY)")

        # Build message list with optional system prompt
        oai_messages: list[dict] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)

        # Convert Anthropic tool schema → OpenAI tool schema
        oai_tools = []
        for t in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            })

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        response = await self._deepseek_client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        msg = choice.message

        content_text = msg.content or ""
        tool_calls = []

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    input_data = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    input_data = {"raw": tc.function.arguments}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": input_data,
                })

        # Map OpenAI finish_reason → Anthropic stop_reason for compatibility
        finish_map = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "content_filter": "end_turn",
        }
        stop_reason = finish_map.get(choice.finish_reason or "stop", "end_turn")

        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "stop_reason": stop_reason,
            "usage": {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            "model_used": model,
        }

    async def _call_ollama(
        self,
        model: str,
        messages: list[dict],
        system: str,
        max_tokens: int,
    ) -> dict:
        """Call Ollama local API for air-gapped mode."""
        ollama_model = model.replace("ollama/", "")

        ollama_messages = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        ollama_messages.extend(messages)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": ollama_model,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
            )
            response.raise_for_status()
            data = await response.json()

        return {
            "content": data.get("message", {}).get("content", ""),
            "tool_calls": [],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            },
        }

    async def _call_glm_anthropic(
        self,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int,
    ) -> dict:
        """
        Call GLM via Z.AI using the Anthropic-compatible endpoint.
        Z.AI exposes https://api.z.ai/api/anthropic which speaks the Anthropic SDK
        protocol — so we get native tool_use, streaming, and the same response format.
        """
        if not settings.glm_api_key:
            raise RuntimeError("GLM API key not configured")

        # Create a one-off Anthropic client pointed at Z.AI
        glm_client = anthropic.Anthropic(
            api_key=settings.glm_api_key,
            base_url=settings.glm_base_url,
        )

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = glm_client.messages.create(**kwargs)

        content_text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }

    async def _call_glm(
        self,
        model: str,
        messages: list[dict],
        system: str,
        max_tokens: int,
    ) -> dict:
        """
        Call GLM via OpenAI-compatible API (legacy fallback, no tool_use).
        Used only if Z.AI endpoint is unavailable.
        """
        if not settings.glm_api_key:
            raise RuntimeError("GLM API key not configured")

        glm_messages = []
        if system:
            glm_messages.append({"role": "system", "content": system})
        glm_messages.extend(messages)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.glm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.glm_api_key}"},
                json={
                    "model": model,
                    "messages": glm_messages,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json() if not hasattr(response.json, "__await__") else await response.json()

        choice = data.get("choices", [{}])[0]
        return {
            "content": choice.get("message", {}).get("content", ""),
            "tool_calls": [],
            "stop_reason": choice.get("finish_reason", "stop"),
            "usage": data.get("usage", {}),
        }

    async def call_llm_with_tools(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        tool_handlers: Optional[dict] = None,
        max_iterations: int = 10,
        terminal_tools: Optional[set] = None,
    ) -> dict:
        """
        Call Claude with tool_use and automatically handle tool calls in a loop.

        Args:
            messages: Conversation messages.
            system: System prompt.
            tool_handlers: Dict mapping tool names to async handler functions.
            max_iterations: Max tool call iterations to prevent infinite loops.

        Returns:
            Final response dict with accumulated content.
        """
        system = system or self.system_prompt
        tool_handlers = tool_handlers or {}
        terminal_tools = terminal_tools or set()
        accumulated_content = ""
        current_messages = list(messages)

        for iteration in range(max_iterations):
            response = await self.call_llm(
                messages=current_messages,
                system=system,
            )

            accumulated_content += response.get("content", "")

            # If no tool calls, we're done
            if not response.get("tool_calls"):
                response["content"] = accumulated_content
                return response

            # Process each tool call
            # Add assistant message with tool use
            assistant_content = []
            if response.get("content"):
                assistant_content.append({"type": "text", "text": response["content"]})
            for tc in response["tool_calls"]:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
            current_messages.append({"role": "assistant", "content": assistant_content})

            # Execute tool handlers and collect results
            tool_results = []
            for tc in response["tool_calls"]:
                handler = tool_handlers.get(tc["name"])
                if handler:
                    try:
                        result = await handler(tc["input"])
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": json.dumps(result) if isinstance(result, (dict, list)) else str(result),
                        })
                    except Exception as e:
                        logger.error(f"Tool {tc['name']} failed: {e}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": f"Error: {str(e)}",
                            "is_error": True,
                        })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": f"Tool '{tc['name']}' not found",
                        "is_error": True,
                    })

            current_messages.append({"role": "user", "content": tool_results})

            # If any terminal tool was called, stop the loop immediately —
            # no need for the model to write a follow-up summary.
            called_names = {tc["name"] for tc in response["tool_calls"]}
            if terminal_tools and called_names & terminal_tools:
                response["content"] = accumulated_content
                return response

        # Max iterations reached
        response["content"] = accumulated_content
        return response

    def log(self, message: str, level: str = "info", **extra):
        """
        Structured log with phase context.
        Extra kwargs are included as structured fields (project_id, model, etc.).
        """
        extra["phase"] = self.phase_number
        # Use the logging extra dict so formatters can pick up structured fields
        getattr(logger, level)(
            "[%s:%s] %s", self.phase_number, self.phase_name, message,
            extra=extra,
            stacklevel=2,
        )
