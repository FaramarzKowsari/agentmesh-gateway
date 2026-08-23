from __future__ import annotations

from pathlib import Path

import typer
import uvicorn

from agentmesh import simulation

app = typer.Typer(no_args_is_help=True, help="AgentMesh Gateway CLI")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8787, help="Bind port"),
    reload: bool = typer.Option(False, help="Reload on source changes"),
) -> None:
    """Run the AgentMesh HTTP gateway."""
    uvicorn.run("agentmesh.api.app:app", host=host, port=port, reload=reload)


@app.command()
def version() -> None:
    """Print the package version."""
    from agentmesh import __version__

    typer.echo(__version__)


@app.command()
def simulate(
    providers: Path = typer.Option(..., exists=True, readable=True, help="Provider JSON file"),
    trace: Path = typer.Option(..., exists=True, readable=True, help="Request trace JSONL file"),
    policies: str = typer.Option(
        "ordered,latency,cost,quality,balanced",
        help="Comma-separated baseline policies",
    ),
    output: Path | None = typer.Option(None, help="Optional output path"),
    format: str = typer.Option("json", help="Output format: json or csv"),
) -> None:
    """Replay a deterministic no-network routing trace."""
    try:
        specs = simulation.load_provider_specs(providers)
        rows = simulation.load_trace(trace)
        selected_policies = simulation.parse_policies(policies)
        result = simulation.simulate(specs, rows, selected_policies)
        if format == "json":
            rendered = simulation.render_json(result)
        elif format == "csv":
            rendered = simulation.render_csv(result)
        else:
            raise ValueError("format must be json or csv")
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if output is None:
        typer.echo(rendered, nl=False)
    else:
        output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    app()
