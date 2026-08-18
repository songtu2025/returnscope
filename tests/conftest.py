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


@pytest.fixture(scope="session")
def seekway_business_baseline_files() -> tuple[Path, Path]:
    returns_path = PROJECT_ROOT / "input_data" / "SEEKWAY_US_.csv"
    products_path = PROJECT_ROOT / "input_data" / "产品信息_20231103.xlsx"
    missing = [path.name for path in (returns_path, products_path) if not path.exists()]
    if missing:
        pytest.skip(f"缺少本地业务基线文件：{'、'.join(missing)}")
    return returns_path, products_path
