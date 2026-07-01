# Wrapper for Ollama/vLLM local requests
import httpx

from backend.config import CLASSIFY_TIMEOUT_MS, GENERATE_TIMEOUT_MS, settings


async def llm_call(prompt: str, *, timeout_ms: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            response = await client.post(
                settings.local_model_endpoint,
                json={"prompt": prompt},
            )
            return response.text
    except httpx.TimeoutException as exc:
        raise TimeoutError(f"Inference call exceeded {timeout_ms}ms budget") from exc
    except httpx.ConnectError as exc:
        raise ConnectionError("Unable to reach local inference server") from exc


async def classify_call(prompt: str) -> str:
    return await llm_call(prompt, timeout_ms=CLASSIFY_TIMEOUT_MS)


async def generate_call(prompt: str) -> str:
    return await llm_call(prompt, timeout_ms=GENERATE_TIMEOUT_MS)
