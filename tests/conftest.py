import os
import shutil
import tempfile
from pathlib import Path

import pytest

from return_semantics.taxonomy import load_listing_claims, load_taxonomy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="return-semantics-pytest-"))

os.environ["WEBAPP_DATA_DIR"] = str(TEST_RUNTIME_ROOT)
os.environ.pop("WEBAPP_DATABASE_PATH", None)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    shutil.rmtree(TEST_RUNTIME_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def taxonomy():
    return load_taxonomy(PROJECT_ROOT / "config" / "taxonomy_water_shoes.json")


@pytest.fixture(scope="session")
def claims():
    return load_listing_claims(PROJECT_ROOT / "config" / "listing_claims_sk001.json")
