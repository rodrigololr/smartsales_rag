"""The documentation gate must inspect project docs, not installed packages."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_spec_contracts


class SpecDiscoveryTests(unittest.TestCase):
    def check_examples(self, root: Path) -> None:
        with patch.object(test_spec_contracts, "ROOT", root):
            test_spec_contracts.Contracts("test_python_examples_compile").test_python_examples_compile()

    def test_installed_package_markdown_is_outside_the_documentation_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dependency = root / ".venv" / "Lib" / "site-packages" / "example"
            dependency.mkdir(parents=True)
            (dependency / "README.md").write_text("```python\nfrom _typeshed import ...\n```\n")
            (root / "README.md").write_text("```python\nanswer = 42\n```\n")
            self.check_examples(root)

    def test_nested_project_spec_examples_are_still_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = root / "specs" / "components"
            spec.mkdir(parents=True)
            (spec / "broken.md").write_text("```python\ndef broken(\n```\n")
            with self.assertRaises(SyntaxError):
                self.check_examples(root)

    def test_root_document_examples_are_still_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("```python\ndef broken(\n```\n")
            with self.assertRaises(SyntaxError):
                self.check_examples(root)
