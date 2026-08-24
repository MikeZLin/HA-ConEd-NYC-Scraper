from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import ModuleType


def _load_const() -> ModuleType:
    path = Path(__file__).parents[1] / "custom_components/coned_connect/const.py"
    spec = importlib.util.spec_from_file_location("coned_connect_const", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConnectorUrlTests(unittest.TestCase):
    def test_url_and_port_are_combined(self) -> None:
        const = _load_const()

        self.assertEqual(
            "http://collector.local:8123",
            const.build_api_url("http://collector.local", 8123),
        )

    def test_selected_port_replaces_url_port_and_preserves_path(self) -> None:
        const = _load_const()

        self.assertEqual(
            "https://example.test:9443/coned",
            const.build_api_url("https://example.test:8000/coned/", 9443),
        )

    def test_legacy_complete_url_remains_unchanged_without_port(self) -> None:
        const = _load_const()

        self.assertEqual(
            "http://collector.local:8000",
            const.build_api_url("http://collector.local:8000", None),
        )

    def test_invalid_scheme_is_rejected(self) -> None:
        const = _load_const()

        with self.assertRaises(ValueError):
            const.build_api_url("ftp://collector.local", 8000)


if __name__ == "__main__":
    unittest.main()
