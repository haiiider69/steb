"""Smoke test: the package and all planned subpackages import cleanly."""

import importlib

import pytest

SUBPACKAGES = [
    "steb",
    "steb.cli",
    "steb.config",
    "steb.capture",
    "steb.ingest",
    "steb.store",
    "steb.retrieval",
    "steb.agent",
    "steb.mcp_server",
    "steb.mcp_client",
    "steb.web",
]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_module_imports_and_is_documented(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__doc__ and module.__doc__.strip(), f"{name} is missing a module docstring"


def test_version() -> None:
    import steb

    assert isinstance(steb.__version__, str)
