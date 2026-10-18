import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from copilot.adapters.csv_folder import CsvFolderAdapter
from copilot.ingest import ingest_folder
from copilot.sandbox.bank import Sandbox
from copilot.store import Store

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "samples" / "demo_business"
SYNTHETIC_DIR = ROOT / "data" / "synthetic"
BIZ = "biz-kopi"


@pytest.fixture(autouse=True)
def _offline(request, monkeypatch):
    """Offline tests never see an API key, so nothing (e.g. the UI's assistant picker) can reach
    the paid API. An empty env var also stops .env from being loaded over it. Live tests opt out."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")


@dataclass
class LoadedScenario:
    store: Store
    sandbox: Sandbox
    business_id: str
    as_of: date
    truth: dict[str, Any]


@pytest.fixture(scope="module")
def load_scenario():
    """Ingest a synthetic scenario (categorised) with the sandbox clock set to its as-of date."""
    cache: dict[str, LoadedScenario] = {}

    def load(name: str) -> LoadedScenario:
        if name not in cache:
            folder = SYNTHETIC_DIR / name
            truth = json.loads((folder / "ground_truth.json").read_text(encoding="utf-8"))
            store = Store(":memory:")
            ingest_folder(store, folder)
            sandbox = Sandbox(store)
            as_of = date.fromisoformat(truth["as_of"])
            sandbox.set_today(truth["business_id"], as_of)
            cache[name] = LoadedScenario(store, sandbox, truth["business_id"], as_of, truth)
        return cache[name]

    return load


@pytest.fixture
def sample_dir() -> Path:
    return SAMPLE_DIR


@pytest.fixture
def sample_import():
    return CsvFolderAdapter().load(SAMPLE_DIR)


@pytest.fixture
def store(sample_import):
    s = Store(":memory:")
    s.save_import(sample_import)
    yield s
    s.close()


@pytest.fixture
def sandbox(store):
    return Sandbox(store)
