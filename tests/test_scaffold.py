"""Minimal test keeping the architecture-only scaffold CI-valid."""


def test_package_is_importable() -> None:
    import hermes_edu

    assert hermes_edu.__name__ == "hermes_edu"
