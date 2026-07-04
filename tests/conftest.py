import pytest

_BITBUCKET_ENV_VARS = [
    "BITBUCKET_TOKEN",
    "BITBUCKET_EMAIL",
    "BITBUCKET_API_TOKEN",
    "BITBUCKET_DEFAULT_WORKSPACE",
    "BITBUCKET_TOOLSETS",
    "BITBUCKET_READ_ONLY",
    "BITBUCKET_BASE_URL",
]


@pytest.fixture(autouse=True)
def _clean_bitbucket_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _BITBUCKET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
