from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from newsresearch.common import Config, utc
from newsresearch.demo import baseline, source
from newsresearch.runtime import Research


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Research]:
    research = Research(tmp_path / "protected", config=Config(max_attempts_per_run=2))
    yield research
    research.close()


@pytest.fixture
def prepared(engine: Research) -> tuple[Research, dict[str, str], Any]:
    versions = baseline(engine, "reviewer:test")

    def run(operation: str, payload: dict[str, Any] | None = None) -> Any:
        return engine.execute(
            operation,
            payload or {},
            objective="Test research invariant",
            actor="reviewer:test",
            versions=versions,
        )

    dataset = run(
        "ingest",
        {
            "articles": [
                source("a", "A service outage was reported.\n\nThe service later recovered."),
                source("b", "Another outlet repeats the service outage report."),
                source("c", "A trial was announced; effects remain uncertain."),
            ],
            "retrieval": {"source": "test synthetic fixture", "retrieved_at": utc(), "parameters": {}},
        },
    )
    versions["dataset"] = dataset["id"]
    grouping = run(
        "dossiers",
        {
            "dossiers": [
                {
                    "id": "d1",
                    "members": [
                        {"source": dataset["sources"][0], "assignment": "confirmed"},
                        {"source": dataset["sources"][1], "assignment": "duplicate"},
                    ],
                },
                {"id": "d2", "members": [{"source": dataset["sources"][2], "assignment": "confirmed"}]},
            ]
        },
    )
    versions["dossiers"] = grouping["id"]
    return engine, versions, run
