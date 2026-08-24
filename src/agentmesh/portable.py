from __future__ import annotations

import sys
from collections.abc import Sequence

from agentmesh.cli import app


def normalized_argv(argv: Sequence[str]) -> list[str]:
    """Default a double-click/no-argument launch to the HTTP gateway."""
    normalized = list(argv)
    if len(normalized) == 1:
        normalized.append("serve")
    return normalized


def main() -> None:
    """Run the portable CLI, starting the gateway when no command is supplied."""
    sys.argv[:] = normalized_argv(sys.argv)
    app()


if __name__ == "__main__":
    main()
