"""python -m bitbucket_mcp / uvx エントリポイント。"""

import argparse
import sys

from bitbucket_mcp.auth import AuthConfigError, resolve_auth_header
from bitbucket_mcp.config import Settings
from bitbucket_mcp.server import create_server


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bitbucket-mcp")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        settings = Settings()
        resolve_auth_header(settings)
    except AuthConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    transport = "streamable-http" if args.transport == "http" else "stdio"
    mcp = create_server(settings, host=args.host, port=args.port)
    mcp.run(transport=transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
