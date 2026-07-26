class FakeTimeout:
    last_timeout: float | None = None

    def __init__(self, timeout: float) -> None:
        type(self).last_timeout = timeout

    async def __aenter__(self) -> "FakeTimeout":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        raise TimeoutError


def forbidden_wait_for(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise AssertionError("caller-owned timeout must not use asyncio.wait_for")
