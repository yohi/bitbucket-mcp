import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import pipelines

BASE = "https://api.bitbucket.org/2.0"


async def test_list_pipelines(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(mcp, "list_pipelines", {"repo_slug": "r", "sort": "-created_on"})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/"
    assert request.url.params["sort"] == "-created_on"


async def test_get_pipeline_steps(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "get_pipeline",
        {"repo_slug": "r", "pipeline_uuid": "{u}", "action": "steps"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/{u}/steps"


async def test_get_pipeline_step_log_text(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(text="log output")
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp,
        "get_pipeline",
        {
            "repo_slug": "r",
            "pipeline_uuid": "{u}",
            "action": "step_log",
            "step_uuid": "{s}",
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/{u}/steps/{s}/log"
    assert structured == {"content": "log output"}


async def test_get_pipeline_step_log_requires_step_uuid(register_toolset, call_tool) -> None:
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    with pytest.raises(ToolError, match="step_uuid"):
        await call_tool(
            mcp,
            "get_pipeline",
            {"repo_slug": "r", "pipeline_uuid": "{u}", "action": "step_log"},
        )


async def test_run_pipeline_body(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"uuid": "{u}"})
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "run_pipeline",
        {
            "repo_slug": "r",
            "target": {"ref_type": "branch", "ref_name": "main"},
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/"
    assert request.read() == (
        b'{"target":{"ref_type":"branch","ref_name":"main","type":"pipeline_ref_target"}}'
    )


async def test_run_pipeline_body_includes_selector(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"uuid": "{u}"})
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "run_pipeline",
        {
            "repo_slug": "r",
            "target": {
                "ref_type": "branch",
                "ref_name": "main",
                "selector": {"type": "custom"},
            },
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.read() == (
        b'{"target":{"ref_type":"branch","ref_name":"main",'
        b'"type":"pipeline_ref_target","selector":{"type":"custom"}}}'
    )


async def test_stop_pipeline_path(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=204)
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(mcp, "stop_pipeline", {"repo_slug": "r", "pipeline_uuid": "{u}"})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/{u}/stopPipeline"


async def test_pipeline_write_tools_absent_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(pipelines.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "run_pipeline" not in names
    assert "stop_pipeline" not in names
    assert "list_pipelines" in names
