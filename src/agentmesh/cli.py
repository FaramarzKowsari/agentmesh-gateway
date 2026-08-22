from __future__ import annotations

import typer
import uvicorn

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


if __name__ == "__main__":
    app()
