from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_html() -> Path:
    return FIXTURES_DIR / "minimal.html"


@pytest.fixture
def tmp_pptx(tmp_path: Path) -> Path:
    return tmp_path / "output.pptx"
