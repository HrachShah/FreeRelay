"""
FreeRelay CLI — Simplified one-command experience
===================================================
"""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

app = typer.Typer(
    name="freerelay",
    help="FreeRelay - AI gateway. Run freerelay to start!",
    add_completion=False,
)
console = Console()


def _setup_env_file() -> None:
    """Create .env file with defaults if it doesn't exist."""
    env_path = Path(".env")

    if env_path.exists():
        return

    console.print(
        "[yellow]No .env file found. Creating default configuration...[/yellow]\n"
    )

    content = """# FreeRelay Configuration
# Mode: free, paid, or auto (default)
FREERELAY_MODE=auto

# Free providers (add your API keys here)
# Get free keys from: Groq | Google | OpenRouter | Together | Mistral
# GROQ_API_KEY=your_key_here
# GOOGLE_AI_KEY=your_key_here

# Paid providers (optional)
# OPENAI_API_KEY=your_key_here
# ANTHROPIC_API_KEY=your_key_here

# Server settings
FREERELAY_PORT=8000
"""
    with open(env_path, "w") as f:
        f.write(content)

    console.print("[green]Created .env file with auto mode![/green]")
    console.print("[dim]Add API keys to .env to use real LLM providers.[/dim]")
    console.print("[dim]Run 'freerelay setup' to add keys interactively.[/dim]")


def _setup_env_interactive() -> None:
    """Interactive setup to add API keys."""
    env_path = Path(".env")

    console.print("[bold cyan]Select Mode:[/bold cyan]")
    console.print(
        "  [green]free[/green] - Use only free providers (Groq, Google, etc.)"
    )
    console.print(
        "  [yellow]paid[/yellow] - Use only paid providers (OpenAI, Anthropic)"
    )
    console.print(
        "  [blue]auto[/blue]  - Use free by default, paid for complex tasks (recommended)\n"
    )

    mode = Prompt.ask(
        "[cyan]Choose mode",
        choices=["free", "paid", "auto"],
        default="auto",
    )

    free_keys = {
        "GROQ_API_KEY": "Groq (https://console.groq.com/keys)",
        "GOOGLE_AI_KEY": "Google AI (https://aistudio.google.com/apikey)",
        "OPENROUTER_API_KEY": "OpenRouter (https://openrouter.ai/keys)",
        "TOGETHER_API_KEY": "Together AI (https://api.together.xyz)",
        "MISTRAL_API_KEY": "Mistral (https://console.mistral.ai/api-keys)",
    }

    paid_keys = {
        "OPENAI_API_KEY": "OpenAI (https://platform.openai.com/api-keys)",
        "ANTHROPIC_API_KEY": "Anthropic (https://console.anthropic.com/settings/keys)",
    }

    content = [
        "# FreeRelay Configuration\n",
        "\n# Mode: free, paid, or auto\n",
        f"FREERELAY_MODE={mode}\n",
    ]

    console.print("\n[bold cyan]Free Provider Keys:[/bold cyan]")
    for key, desc in free_keys.items():
        add_key = Prompt.ask(f"Add {desc}?", choices=["y", "n"], default="n")
        if add_key.lower() == "y":
            api_key = Prompt.obscurored(f"  Enter {key}:")
            if api_key.strip():
                content.append(f"{key}={api_key.strip()}\n")

    console.print("\n[bold cyan]Paid Provider Keys (optional):[/bold cyan]")
    for key, desc in paid_keys.items():
        add_key = Prompt.ask(f"Add {desc}?", choices=["y", "n"], default="n")
        if add_key.lower() == "y":
            api_key = Prompt.obscurored(f"  Enter {key}:")
            if api_key.strip():
                content.append(f"{key}={api_key.strip()}\n")

    content.append("\n# Server settings\nFREERELAY_PORT=8000\n")

    with open(env_path, "w") as f:
        f.writelines(content)

    console.print(f"\n[green]Created .env file with {mode} mode![/green]\n")


@app.command()
def start(
    port: int = 8000,
    demo: bool = False,
) -> None:
    """Start the FreeRelay AI gateway."""
    import uvicorn

    # Auto-setup .env if needed
    if not Path(".env").exists():
        _setup_env_file()

    # Set port
    os.environ["FREERELAY_PORT"] = str(port)

    if demo:
        os.environ["FREERELAY_DEMO_MODE"] = "true"

    console.print(
        Panel.fit(
            "[bold cyan]FreeRelay AI Gateway[/bold cyan]\n"
            f"Starting on [green]http://localhost:{port}[/green]\n"
            f"[dim]API: http://localhost:{port}/v1/chat/completions[/dim]\n"
            f"[dim]Docs: http://localhost:{port}/docs[/dim]",
            border_style="cyan",
        )
    )

    uvicorn.run(
        "freerelay.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )


@app.command(name="run")
def run(
    port: int = 8000,
) -> None:
    """Same as start - runs the gateway."""
    start(port=port, demo=False)


@app.command()
def demo() -> None:
    """Start FreeRelay in demo mode (works without API keys)."""
    start(demo=True)


@app.command()
def status() -> None:
    """Check provider status."""
    import httpx

    try:
        resp = httpx.get("http://localhost:8000/v1/stats", timeout=5)
        data = resp.json()
    except Exception:
        console.print("[red]✗ FreeRelay not running. Start with: freerelay[/red]")
        raise typer.Exit(1)

    from rich.table import Table

    table = Table(title="⚡ FreeRelay Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Requests", justify="right")

    for p in data.get("providers", []):
        state = p.get("circuit", {}).get("state", "?")
        color = {"CLOSED": "green", "HALF_OPEN": "yellow", "OPEN": "red"}.get(
            state, "white"
        )

        table.add_row(
            p["name"],
            f"[{color}]{state}[/{color}]",
            str(p.get("request_count", 0)),
        )

    console.print(table)


@app.command()
def benchmark(
    requests: int = typer.Option(10, "--requests", help="Number of requests"),
    concurrent: int = typer.Option(3, "--concurrent", help="Concurrent requests"),
) -> None:
    """Run a quick benchmark."""
    import asyncio
    import time

    import httpx

    payload = {
        "messages": [{"role": "user", "content": "Say hello in 3 words or less."}],
        "max_tokens": 10,
    }

    async def run() -> None:
        latencies = []

        async with httpx.AsyncClient() as client:

            async def send():
                start = time.time()
                try:
                    r = await client.post(
                        "http://localhost:8000/v1/chat/completions",
                        json=payload,
                        timeout=30,
                    )
                    if r.status_code == 200:
                        latencies.append((time.time() - start) * 1000)
                except Exception:
                    pass

            await asyncio.gather(*[send() for _ in range(requests)])

        if latencies:
            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]

            console.print(
                Panel.fit(
                    f"[bold]Benchmark Results[/bold]\n\n"
                    f"Requests:  {requests}\n"
                    f"Success:   {len(latencies)}\n"
                    f"p50:       {p50:.0f}ms\n"
                    f"p95:       {p95:.0f}ms",
                    border_style="green",
                )
            )
        else:
            console.print("[red]No successful requests. Is FreeRelay running?[/red]")

    asyncio.run(run())


@app.command()
def open_dashboard() -> None:
    """Open the dashboard in browser."""
    webbrowser.open("http://localhost:8000/dashboard")


@app.command()
def setup() -> None:
    """Interactive setup to add API keys."""
    _setup_env_interactive()
    console.print("[green]Setup complete! Run [bold]freerelay[/bold] to start.[/green]")


# Default command - just run "freerelay" without any subcommand
@app.command()
def main() -> None:
    """Start FreeRelay (default command)."""
    start(port=8000, demo=False)


if __name__ == "__main__":
    app()
