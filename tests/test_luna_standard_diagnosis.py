import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import diagnose_luna_standard as diagnosis
finally:
    sys.path.pop(0)


def test_metadata_does_not_return_source_output_or_error_text():
    private = "PRIVATE ARTICLE AND MODEL TEXT"
    saved = {"raw_response": {"failure": "codex_turn_failed_unknown_outcome", "exit_code": 1,
        "stdout": private, "stderr": "stream disconnected: unexpected status 429 " + private,
        "events": [{"type": "error", "message": "Reconnecting... 1/5 (403 " + private + ")"},
                   {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps({"article": private})}},
                   {"type": "turn.failed", "error": {"message": "usage limit " + private}}]}}
    result = diagnosis.response_metadata(saved)
    assert private not in json.dumps(result)
    assert result["failure"] == "codex_turn_failed_unknown_outcome"
    assert result["final_json_objects"] == [True]
    assert result["errors"][0]["http_statuses"] == ["403"]
    assert "usage_limit" in result["errors"][1]["labels"]
    assert result["stderr"]["http_statuses"] == ["429"]
    assert result["original_hold_unchanged"]
