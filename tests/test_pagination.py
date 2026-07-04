from bitbucket_mcp.pagination import MAX_PAGELEN, page_params


def test_default_pagelen_when_none() -> None:
    assert page_params() == {"pagelen": 25}


def test_page_included_when_given() -> None:
    assert page_params(page=2) == {"page": 2, "pagelen": 25}


def test_pagelen_clamped_to_max() -> None:
    assert page_params(pagelen=500)["pagelen"] == MAX_PAGELEN


def test_pagelen_floored_to_one() -> None:
    assert page_params(pagelen=0)["pagelen"] == 1


def test_custom_pagelen_passthrough() -> None:
    assert page_params(page=1, pagelen=50) == {"page": 1, "pagelen": 50}
