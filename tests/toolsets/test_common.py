"""認証フックのテスト。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from bitbucket_mcp.auth import AuthConfigError, AuthProvider, StaticAuthProvider
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient, OAuthTokenResponse
from bitbucket_mcp.toolsets._common import (
    AutoLoginController,
    RegisterContext,
    build_body,
    create_toolset_context_from_register_args,
    perform_auto_login,
    request_repo_json,
    request_repo_text,
    require_auth,
    wrap_tool,
)


def test_build_body_omits_none_values() -> None:
    assert build_body(title="Bug", description=None) == {"title": "Bug"}


def test_create_toolset_context_from_register_args_preserves_options() -> None:
    client = object()
    mcp = object()
    ctx = create_toolset_context_from_register_args(
        mcp,
        client,
        True,
        "workspace",
        StaticAuthProvider("Bearer test-token"),
    )
    assert ctx.mcp is mcp
    assert ctx.client is client
    assert ctx.read_only is True
    assert ctx.default_workspace == "workspace"


type _RegisteredTool = tuple[Callable[..., Awaitable[str]], ToolAnnotations]


class _ToolRecorder:
    def __init__(self) -> None:
        self.tools: list[_RegisteredTool] = []

    def add_tool(
        self,
        fn: Callable[..., Awaitable[str]],
        *,
        annotations: ToolAnnotations,
    ) -> None:
        self.tools.append((fn, annotations))


def test_register_tools_orders_all_categories_when_not_read_only() -> None:
    async def always_tool() -> str:
        return "always"

    async def read_tool() -> str:
        return "read"

    async def write_tool() -> str:
        return "write"

    async def destructive_tool() -> str:
        return "destructive"

    always_annotations = ToolAnnotations(openWorldHint=False)
    read_annotations = ToolAnnotations(readOnlyHint=True)
    write_annotations = ToolAnnotations(readOnlyHint=False)
    destructive_annotations = ToolAnnotations(destructiveHint=True)
    recorder = _ToolRecorder()
    context = RegisterContext(recorder, None, read_only=False)

    context.register_tools(
        always=[(always_tool, always_annotations)],
        read=[(read_tool, read_annotations)],
        write=[(write_tool, write_annotations)],
        destructive=[(destructive_tool, destructive_annotations)],
    )

    assert recorder.tools == [
        (always_tool, always_annotations),
        (read_tool, read_annotations),
        (write_tool, write_annotations),
        (destructive_tool, destructive_annotations),
    ]


def test_register_tools_excludes_write_categories_when_read_only() -> None:
    async def always_tool() -> str:
        return "always"

    async def read_tool() -> str:
        return "read"

    async def write_tool() -> str:
        return "write"

    async def destructive_tool() -> str:
        return "destructive"

    always_annotations = ToolAnnotations(openWorldHint=False)
    read_annotations = ToolAnnotations(readOnlyHint=True)
    write_annotations = ToolAnnotations(readOnlyHint=False)
    destructive_annotations = ToolAnnotations(destructiveHint=True)
    recorder = _ToolRecorder()
    context = RegisterContext(recorder, None, read_only=True)

    context.register_tools(
        always=[(always_tool, always_annotations)],
        read=[(read_tool, read_annotations)],
        write=[(write_tool, write_annotations)],
        destructive=[(destructive_tool, destructive_annotations)],
    )

    assert recorder.tools == [
        (always_tool, always_annotations),
        (read_tool, read_annotations),
    ]


type _RequestCall = tuple[
    str,
    str,
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]


async def test_register_context_request_json_resolves_workspace() -> None:
    calls: list[_RequestCall] = []

    class _Client:
        async def request(
            self,
            method: str,
            path: str,
            *,
            query: dict[str, object] | None = None,
            body: dict[str, object] | None = None,
            form: dict[str, object] | None = None,
        ) -> dict[str, object]:
            calls.append((method, path, query, body, form))
            return {"ok": True}

    ctx = create_toolset_context_from_register_args(
        object(), _Client(), True, "ws", StaticAuthProvider("Bearer test-token")
    )
    result = await ctx.request_json(
        "workspace",
        "GET",
        "/repositories/{ws}/{repo_slug}",
        path_params={"repo_slug": "repo"},
        query={"page": 1},
    )
    assert result == {"ok": True}
    assert calls == [("GET", "/repositories/workspace/repo", {"page": 1}, None, None)]


async def test_register_context_request_text_resolves_workspace() -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    class _Client:
        async def request_text(
            self,
            method: str,
            path: str,
            *,
            query: dict[str, object] | None = None,
        ) -> str:
            calls.append((method, path, query))
            return "text"

    ctx = create_toolset_context_from_register_args(
        object(), _Client(), True, "ws", StaticAuthProvider("Bearer test-token")
    )
    result = await ctx.request_text(
        "workspace",
        "GET",
        "/repositories/{ws}/{repo_slug}/diff/{spec}",
        path_params={"repo_slug": "repo", "spec": "abc..def"},
    )
    assert result == "text"
    assert calls == [("GET", "/repositories/workspace/repo/diff/abc..def", None)]


async def test_request_repo_json_builds_repository_path() -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    class _Client:
        async def request(
            self,
            method: str,
            path: str,
            *,
            query: dict[str, object] | None = None,
            body: dict[str, object] | None = None,
            form: dict[str, object] | None = None,
        ) -> dict[str, object]:
            calls.append((method, path, query))
            return {"ok": True}

    class _Ctx:
        client = _Client()

        def resolve_workspace(self, workspace: str | None) -> str:
            assert workspace is not None
            return workspace

    result = await request_repo_json(_Ctx(), "workspace", "GET", "repo", "/issues")
    assert result == {"ok": True}
    assert calls == [("GET", "/repositories/workspace/repo/issues", None)]


async def test_request_repo_text_builds_repository_path() -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    class _Client:
        async def request_text(
            self,
            method: str,
            path: str,
            *,
            query: dict[str, object] | None = None,
        ) -> str:
            calls.append((method, path, query))
            return "text"

    class _Ctx:
        client = _Client()

        def resolve_workspace(self, workspace: str | None) -> str:
            assert workspace is not None
            return workspace

    result = await request_repo_text(_Ctx(), "workspace", "GET", "repo", "/src/x")
    assert result == "text"
    assert calls == [("GET", "/repositories/workspace/repo/src/x", None)]


async def test_request_repo_json_preserves_braces_in_suffix() -> None:
    calls: list[str] = []

    class _Client:
        async def request(self, _method: str, path: str, **_kwargs: object) -> dict[str, object]:
            calls.append(path)
            return {"ok": True}

    class _Ctx:
        client = _Client()

        def resolve_workspace(self, workspace: str | None) -> str:
            assert workspace is not None
            return workspace

    await request_repo_json(
        _Ctx(),
        "workspace",
        "GET",
        "repo",
        "/src/abc/{literal}.txt",
    )
    assert calls == ["/repositories/workspace/repo/src/abc/{literal}.txt"]


async def test_request_repo_text_preserves_braces_in_suffix() -> None:
    calls: list[str] = []

    class _Client:
        async def request_text(self, _method: str, path: str, **_kwargs: object) -> str:
            calls.append(path)
            return "text"

    class _Ctx:
        client = _Client()

        def resolve_workspace(self, workspace: str | None) -> str:
            assert workspace is not None
            return workspace

    await request_repo_text(
        _Ctx(),
        "workspace",
        "GET",
        "repo",
        "/src/abc/{literal}.txt",
    )
    assert calls == ["/repositories/workspace/repo/src/abc/{literal}.txt"]


async def test_require_auth_passes_when_authenticated() -> None:
    provider = StaticAuthProvider("Bearer x")
    controller = AutoLoginController()

    async def tool() -> str:
        return "ok"

    decorated = require_auth(provider, controller, None, None)(tool)
    assert await decorated() == "ok"


async def test_require_auth_raises_when_not_authenticated_with_oauth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Unauth(AuthProvider):
        async def authorization_header(self) -> str:
            raise RuntimeError

        async def refresh(self) -> None:
            pass

        async def aclose(self) -> None:
            pass

        def is_authenticated(self) -> bool:
            return False

    monkeypatch.setattr(
        "bitbucket_mcp.toolsets._common.display_available",
        lambda: True,
    )
    store = CredentialStore(tmp_path / "creds.json")
    controller = AutoLoginController()
    oauth_client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:0/callback",
        scopes=["account"],
    )

    async def tool() -> str:
        return "ok"

    decorated = require_auth(
        _Unauth(),
        controller,
        oauth_client,
        store,
    )(tool)
    with pytest.raises(ToolError, match="ブラウザ"):
        await decorated()
    await controller.shutdown()
    await oauth_client.aclose()


async def test_require_auth_raises_when_already_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Unauth(AuthProvider):
        def is_authenticated(self) -> bool:
            return False

        async def authorization_header(self) -> str:
            raise RuntimeError

        async def refresh(self) -> None:
            pass

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(
        "bitbucket_mcp.toolsets._common.display_available",
        lambda: True,
    )
    store = CredentialStore(tmp_path / "creds.json")
    controller = AutoLoginController()
    oauth_client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:0/callback",
        scopes=["account"],
    )

    async def tool() -> str:
        return "ok"

    decorated = require_auth(
        _Unauth(),
        controller,
        oauth_client,
        store,
    )(tool)
    with pytest.raises(ToolError, match="ブラウザ"):
        await decorated()
    with pytest.raises(ToolError, match="処理中"):
        await decorated()
    await controller.shutdown()
    await oauth_client.aclose()


def test_wrap_tool_raises_auth_config_error_without_provider() -> None:
    with pytest.raises(AuthConfigError, match="auth_provider"):
        wrap_tool(None, None, None)


async def test_auto_login_releases_controller_after_unexpected_error() -> None:
    controller = AutoLoginController()
    assert controller.start(lambda: (_ for _ in ()).throw(RuntimeError("boom"))) is True
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert controller.is_running() is False


def oauth_flow_error(message: str) -> Exception:
    from bitbucket_mcp.oauth import OAuthFlowError

    return OAuthFlowError(message)


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (
            TimeoutError("https://auth.example/?code=authorization-code"),
            "Automatic login timed out",
        ),
        (
            oauth_flow_error("access_token=access-token&refresh_token=refresh-token"),
            "Automatic login OAuth flow failed",
        ),
        (
            RuntimeError("client_secret=client-secret credential_payload={'access_token': 'x'}"),
            "Unexpected error during automatic login",
        ),
    ],
)
async def test_auto_login_logs_classified_failures_without_credentials(
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_message: str,
) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="bitbucket_mcp.toolsets._common")
    controller = AutoLoginController()

    async def fail() -> None:
        raise error

    assert controller.start(fail) is True
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert controller.is_running() is False
    assert [record.getMessage() for record in caplog.records] == [expected_message]
    assert all(record.exc_info is None for record in caplog.records)
    log_output = "\n".join(caplog.messages)
    for sensitive_value in (
        "https://auth.example/",
        "authorization-code",
        "access-token",
        "refresh-token",
        "client-secret",
        "credential_payload",
    ):
        assert sensitive_value not in log_output


async def test_auto_login_cancellation_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="bitbucket_mcp.toolsets._common")
    started = asyncio.Event()
    never = asyncio.Event()
    controller = AutoLoginController()

    async def wait_forever() -> None:
        started.set()
        await never.wait()

    assert controller.start(wait_forever) is True
    await started.wait()
    await controller.shutdown()

    assert controller.is_running() is False
    assert caplog.records == []


async def test_auto_login_uses_caller_owned_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="bitbucket_mcp.toolsets._common")
    captured_timeout: float | None = None

    class FakeTimeout:
        def __init__(self, timeout: float) -> None:
            nonlocal captured_timeout
            captured_timeout = timeout

        async def __aenter__(self) -> "FakeTimeout":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            del exc_type, exc, tb
            raise TimeoutError

    def forbidden_wait_for(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("caller-owned timeout must not use asyncio.wait_for")

    def fake_timeout(timeout: float) -> FakeTimeout:
        return FakeTimeout(timeout)

    monkeypatch.setattr("bitbucket_mcp.toolsets._common.asyncio.wait_for", forbidden_wait_for)
    monkeypatch.setattr("bitbucket_mcp.toolsets._common.asyncio.timeout", fake_timeout)

    controller = AutoLoginController()

    async def complete() -> None:
        return None

    assert controller.start(complete) is True
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert captured_timeout == 300
    assert controller.is_running() is False
    assert [record.getMessage() for record in caplog.records] == ["Automatic login timed out"]


async def test_auto_login_closes_callback_server_when_start_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from bitbucket_mcp.oauth import OAuthFlowError

    class _Callback:
        def __init__(self, **_kwargs: object) -> None:
            self.closed = False

        async def start(self) -> None:
            raise OAuthFlowError("callback failed")

        async def aclose(self) -> None:
            self.closed = True

    callback = _Callback()

    def fake_callback_server(**_kwargs: object) -> _Callback:
        return callback

    monkeypatch.setattr(
        "bitbucket_mcp.toolsets._common.OAuthCallbackServer",
        fake_callback_server,
    )
    oauth_client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:0/callback",
        scopes=["account"],
    )
    provider = StaticAuthProvider("Bearer x")
    store = CredentialStore(tmp_path / "creds.json")
    try:
        with pytest.raises(OAuthFlowError, match="callback failed"):
            await perform_auto_login(provider, oauth_client, store)
    finally:
        await oauth_client.aclose()
    assert callback.closed is True


async def test_perform_auto_login_exchanges_persists_refreshes_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    browser_urls: list[str] = []
    store = CredentialStore(tmp_path / "credentials.json")
    client_closed = False

    class RefreshingProvider(AuthProvider):
        async def authorization_header(self) -> str:
            return "Bearer synthetic-access-token"

        async def refresh(self) -> None:
            stored = store.load()
            assert stored is not None
            assert stored.access_token == "synthetic-access-token"
            assert stored.refresh_token == "synthetic-refresh-token"
            events.append("refresh")

        async def aclose(self) -> None:
            return None

        def is_authenticated(self) -> bool:
            return True

    class FakeCallbackServer:
        def __init__(self, *, host: str, port: int, expected_state: str) -> None:
            assert host == "127.0.0.1"
            assert port == 8976
            self.expected_state = expected_state

        async def start(self) -> None:
            events.append("callback-start")

        async def wait_callback(self) -> tuple[str, str | None]:
            events.append("callback-wait")
            return ("synthetic-authorization-code", self.expected_state)

        async def aclose(self) -> None:
            events.append("callback-close")

    def fake_build_authorize_url(_client: OAuthClient, state: str) -> str:
        assert state == "synthetic-state"
        events.append("authorize")
        return "https://bitbucket.org/authorize?state=synthetic-state"

    async def fake_exchange_code(
        _client: OAuthClient,
        code: str,
    ) -> OAuthTokenResponse:
        assert code == "synthetic-authorization-code"
        events.append("exchange")
        return OAuthTokenResponse(
            access_token="synthetic-access-token",
            refresh_token="synthetic-refresh-token",
            expires_in=600,
            scopes=["account"],
            token_type="bearer",
        )

    def fake_browser_open(url: str) -> bool:
        browser_urls.append(url)
        events.append("browser-open")
        return True

    original_aclose = OAuthClient.aclose

    async def tracked_aclose(client: OAuthClient) -> None:
        nonlocal client_closed
        await original_aclose(client)
        client_closed = True

    monkeypatch.setattr(
        "bitbucket_mcp.toolsets._common.OAuthCallbackServer",
        FakeCallbackServer,
    )
    monkeypatch.setattr(
        "bitbucket_mcp.toolsets._common.generate_state",
        lambda: "synthetic-state",
    )
    monkeypatch.setattr(
        "bitbucket_mcp.toolsets._common.time.time",
        lambda: 1_000,
    )
    monkeypatch.setattr(OAuthClient, "build_authorize_url", fake_build_authorize_url)
    monkeypatch.setattr(OAuthClient, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(OAuthClient, "aclose", tracked_aclose)
    monkeypatch.setattr(
        "bitbucket_mcp.toolsets._common.webbrowser.open",
        fake_browser_open,
    )
    oauth_client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="synthetic-client-id",
        client_secret="synthetic-client-secret",
        redirect_uri="http://127.0.0.1:8976/callback",
        scopes=["account"],
    )

    try:
        await perform_auto_login(RefreshingProvider(), oauth_client, store)
    finally:
        await oauth_client.aclose()

    stored = store.load()
    assert browser_urls == ["https://bitbucket.org/authorize?state=synthetic-state"]
    assert stored is not None
    assert stored.client_id == "synthetic-client-id"
    assert stored.expires_at == 1_600
    assert events == [
        "callback-start",
        "authorize",
        "browser-open",
        "callback-wait",
        "exchange",
        "refresh",
        "callback-close",
    ]
    assert client_closed is True
