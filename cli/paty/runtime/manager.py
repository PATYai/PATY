"""Managed subprocess lifecycle for PATY sidecar services."""

from __future__ import annotations

import asyncio
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass, field

import httpx
from opentelemetry import trace

from paty.hardware.profiles import ResolvedProfile

tracer = trace.get_tracer("paty")


def find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class ManagedProcess:
    """Start, health-check, and stop a subprocess tied to paty's lifecycle."""

    name: str
    cmd: list[str]
    health_path: str = "/v1/models"
    port: int = 0
    process: subprocess.Popen | None = field(default=None, repr=False)
    _port_flag: str = "--port"

    async def start(self, timeout: float = 120.0) -> int:
        """Start the process, wait for health check, return the assigned port."""
        with tracer.start_as_current_span(f"paty.runtime.start.{self.name}") as span:
            self.port = find_free_port()
            span.set_attribute(f"paty.{self.name}.port", self.port)

            full_cmd = [*self.cmd, self._port_flag, str(self.port)]
            span.set_attribute(f"paty.{self.name}.cmd", " ".join(full_cmd))

            self.process = subprocess.Popen(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            await self._wait_for_healthy(timeout)
            return self.port

    async def stop(self, timeout: float = 10.0) -> None:
        """Graceful shutdown: SIGTERM, then SIGKILL if needed."""
        if self.process is None or self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    async def _wait_for_healthy(self, timeout: float) -> None:
        """Poll health endpoint until ready or timeout."""
        url = f"http://127.0.0.1:{self.port}{self.health_path}"
        deadline = asyncio.get_event_loop().time() + timeout
        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                if self.process and self.process.poll() is not None:
                    stderr = ""
                    if self.process.stderr:
                        stderr = self.process.stderr.read().decode()
                    msg = (
                        f"{self.name} exited with code "
                        f"{self.process.returncode}: {stderr[:500]}"
                    )
                    raise RuntimeError(msg)
                try:
                    resp = await client.get(url, timeout=2.0)
                    if resp.status_code == 200:
                        return
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass
                await asyncio.sleep(1.0)

        msg = f"{self.name} did not become healthy within {timeout}s at {url}"
        raise TimeoutError(msg)

    async def warmup(self, model_id: str, timeout: float = 600.0) -> None:
        """Send a short completion request to force the model into memory."""
        url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
                timeout=timeout,
            )
            resp.raise_for_status()


@dataclass
class ManagedLLM:
    """A ManagedProcess plus the resolved model identifier for API requests."""

    process: ManagedProcess
    model_id: str


def create_managed_llm(
    model: str,
    platform: str,
    profile: ResolvedProfile | None = None,
) -> ManagedLLM:
    """Create a ManagedProcess for the LLM inference server.

    Returns a ManagedLLM containing the process and the resolved model_id
    that the OpenAI-compatible client should use in requests.

    Args:
        model: Model key (e.g. "qwen3:4b") or HuggingFace repo path.
        platform: Compute platform ("mlx", "cuda", "cpu").
        profile: Resolved hardware profile with tuning settings.
    """
    # Model key (e.g. "qwen3:8b") → HuggingFace repo
    mlx_models = {
        "qwen3:4b": "mlx-community/Qwen2.5-3B-Instruct-4bit",
        "qwen3:8b": "mlx-community/Qwen2.5-7B-Instruct-4bit",
        "qwen3:14b": "mlx-community/Qwen2.5-14B-Instruct-4bit",
    }
    gguf_models = {
        "qwen3:4b": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "qwen3:8b": "Qwen/Qwen2.5-7B-Instruct-GGUF",
        "qwen3:14b": "Qwen/Qwen2.5-14B-Instruct-GGUF",
    }

    if platform == "mlx":
        hf_repo = mlx_models.get(model, model)
        cmd = [
            sys.executable,
            "-m",
            "mlx_lm.server",
            "--model",
            hf_repo,
        ]
        if profile:
            cmd.extend(
                [
                    "--prompt-cache-size",
                    str(profile.llm_prompt_cache_size),
                    "--max-tokens",
                    str(profile.llm_max_tokens),
                    "--prefill-step-size",
                    str(profile.llm_prefill_step_size),
                ]
            )
        proc = ManagedProcess(
            name="llm",
            cmd=cmd,
            health_path="/v1/models",
        )
        return ManagedLLM(process=proc, model_id=hf_repo)

    # CUDA or CPU — use llama-cpp-python
    hf_repo = gguf_models.get(model, model)
    gpu_layers = "-1" if platform == "cuda" else "0"
    proc = ManagedProcess(
        name="llm",
        cmd=[
            sys.executable,
            "-m",
            "llama_cpp.server",
            "--model",
            hf_repo,
            "--n_gpu_layers",
            gpu_layers,
        ],
        health_path="/v1/models",
    )
    return ManagedLLM(process=proc, model_id=hf_repo)
