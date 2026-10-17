"""Complete untouched tasks only; existing stored key must be injected by launcher."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

from newsresearch.common import Config, ResearchError
from newsresearch.singleton_api_continuation import SingletonContinuationResearch


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        raise ResearchError("Stored OpenAI key unavailable; no request sent")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=False)
    engine = SingletonContinuationResearch(Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-seven-day-validation-20261016-v1"), config=config)
    try:
        result = engine.execute("luna_group_validation", {"phase": "singleton_api_continue_untouched"},
            objective="Finish only the untouched comparisons in the user's original random 100-singleton API sample without retries or budget expansion",
            actor="codex:singleton-api-untouched-continuation")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["id"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
