"""
FreeRelay CLI — Typer-based command-line interface
====================================================
Commands: start, status, benchmark, flush-cache, chaos
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="freerelay",
    help="⚡ FreeRelay — Production AI gateway for free LLM tiers",
    add_completion=False,
)
console = Console()


@app.command()
def start(
    host: str = typer.Option("0.0.0.0", help="Bind address"),
    port: int = typer.Option(8000, help="Port"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
    workers: int = typer.Option(1, help="Number of worker processes"),
    chaos: bool = typer.Option(False, help="Enable chaos engineering mode"),
    log_level: str = typer.Option("info", help="Log level"),
) -> None:
    """Start the FreeRelay AI gateway."""
    import os
    import uvicorn

    if chaos:
        os.environ["FREERELAY_ENABLE_CHAOS"] = "true"

    os.environ["FREERELAY_LOG_LEVEL"] = log_level.upper()

    console.print(Panel.fit(
        "[bold cyan]⚡ FreeRelay AI Gateway[/bold cyan]\n"
        f"Starting on [green]http://{host}:{port}[/green]",
        border_style="cyan",
    ))

    uvicorn.run(
        "freerelay.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=log_level.lower(),
    )


@app.command()
def status() -> None:
    """Check FreeRelay server status and provider health."""
    import httpx

    try:
        resp = httpx.get("http://localhost:8000/v1/stats", timeout=5)
        data = resp.json()
    except Exception:
        console.print("[red]✗ Cannot connect to FreeRelay at localhost:8000[/red]")
        raise typer.Exit(1)

    table = Table(title="⚡ FreeRelay Provider Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Circuit", style="white")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Requests", justify="right")
    table.add_column("Errors", justify="right", style="red")
    table.add_column("p95 Latency", justify="right")

    for p in data.get("providers", []):
        circuit = p.get("circuit", {})
        state = circuit.get("state", "?")
        state_color = {"CLOSED": "green", "HALF_OPEN": "yellow", "OPEN": "red"}.get(state, "white")

        table.add_row(
            p["name"],
            f"[{state_color}]{state}[/{state_color}]",
            f"{p.get('score', 0):.4f}",
            str(p.get("request_count", 0)),
            str(p.get("error_count", 0)),
            f"{p.get('latency_p95_ms', 0):.0f}ms",
        )

    console.print(table)


@app.command()
def benchmark(
    requests: int = typer.Option(20, help="Number of requests to send"),
    concurrent: int = typer.Option(5, help="Concurrent requests"),
) -> None:
    """Run a quick benchmark against the local FreeRelay instance."""
    import asyncio
    import time
    import httpx

    async def _run() -> None:
        payload = {
            "messages": [{"role": "user", "content": "Say hello in one word."}],
            "max_tokens": 10,
        }

        latencies: list[float] = []
        errors = 0

        sem = asyncio.Semaphore(concurrent)

        async def _single(client: httpx.AsyncClient) -> None:
            nonlocal errors
            async with sem:
                start = time.time()
                try:
                    resp = await client.post(
                        "http://localhost:8000/v1/chat/completions",
                        json=payload,
                        timeout=30,
                    )
                    elapsed = (time.time() - start) * 1000
                    if resp.status_code == 200:
                        latencies.append(elapsed)
                    else:
                        errors += 1
                except Exception:
                    errors += 1

        async with httpx.AsyncClient() as client:
            tasks = [_single(client) for _ in range(requests)]
            await asyncio.gather(*tasks)

        if latencies:
            sorted_l = sorted(latencies)
            p50 = sorted_l[len(sorted_l) // 2]
            p95 = sorted_l[int(len(sorted_l) * 0.95)]
            p99 = sorted_l[int(len(sorted_l) * 0.99)]

            console.print(Panel.fit(
                f"[bold]Benchmark Results[/bold]\n\n"
                f"Total:    {requests} requests\n"
                f"Success:  {len(latencies)}\n"
                f"Errors:   {errors}\n"
                f"p50:      {p50:.0f}ms\n"
                f"p95:      {p95:.0f}ms\n"
                f"p99:      {p99:.0f}ms\n"
                f"Mean:     {sum(latencies)/len(latencies):.0f}ms",
                border_style="green",
            ))
        else:
            console.print("[red]All requests failed[/red]")

    asyncio.run(_run())


@app.command(name="flush-cache")
def flush_cache() -> None:
    """Flush the semantic cache."""
    console.print("[yellow]Cache flush not yet implemented (requires Redis)[/yellow]")


@app.command()
def chaos(
    intensity: float = typer.Option(0.3, help="Chaos intensity 0.0-1.0"),
) -> None:
    """Start FreeRelay with chaos engineering enabled."""
    import os
    os.environ["FREERELAY_ENABLE_CHAOS"] = "true"
    os.environ["FREERELAY_CHAOS_INTENSITY"] = str(intensity)

    console.print(f"[red bold]🔥 CHAOS MODE — intensity {intensity}[/red bold]")
    start(chaos=True)


if __name__ == "__main__":
    app()
