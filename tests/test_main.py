import pytest

from bitbucket_mcp import __main__ as entry


def test_arg_parser_defaults() -> None:
    args = entry.build_arg_parser().parse_args([])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000


def test_arg_parser_http() -> None:
    args = entry.build_arg_parser().parse_args(
        ["--transport", "http", "--host", "0.0.0.0", "--port", "9000"]
    )
    assert args.transport == "http"
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_main_runs_stdio_when_credentials_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITBUCKET_TOKEN", "t")
    called: dict[str, object] = {}

    def fake_run(self: object, *args: object, **kwargs: object) -> None:
        called["transport"] = kwargs.get("transport", args[0] if args else None)

    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", fake_run)
    assert entry.main(["--transport", "stdio"]) == 0
    assert called["transport"] == "stdio"
