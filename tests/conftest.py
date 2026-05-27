from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def temp_db_env(tmp_path: Path):
    db_path = tmp_path / "watchagent-test.db"
    old = os.environ.get("WATCHAGENT_DB_PATH")
    os.environ["WATCHAGENT_DB_PATH"] = str(db_path)
    try:
        yield db_path
    finally:
        if old is None:
            os.environ.pop("WATCHAGENT_DB_PATH", None)
        else:
            os.environ["WATCHAGENT_DB_PATH"] = old

