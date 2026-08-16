def test_package_imports():
    import src  # noqa: F401

    assert src.__version__
