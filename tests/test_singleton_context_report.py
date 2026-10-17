"""Output-only diagnostics do not infer source truth or correct original labels."""
import json

from newsresearch.singleton_context_report import replay_failure, warning_cues


def test_literal_positive_warning_is_not_a_negative_label_and_replay_stays_unaccepted():
    reason = "There is insufficient basis to match a focal event."
    assert warning_cues("same_event", reason) == ["insufficient basis to match a focal event"]
    assert warning_cues("uncertain", reason) == []
    assert warning_cues("same_event", "Both report the same invented announcement.") == []
    assert replay_failure({}, {"status": "incomplete", "model": "gpt-6-luna"}) == "singleton_api_incomplete_or_wrong_model"
    from test_singleton_context_api import context
    from newsresearch.singleton_context_contract import build_request
    request = build_request(context("a", "Fictional source about an invented announcement."),
                            context("b", "Fictional source about a synthetic event."), {})
    answer = {"label": "same_event", "support_span_ids": ["A1", "B1"], "reason": "Fictional only."}

    def response(value):
        return {"model": "gpt-6-luna", "status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(value)}]}]}

    assert replay_failure(request, response(answer)) == "stored_output_now_structurally_valid_but_not_accepted"
    assert replay_failure(request, response({**answer, "support_span_ids": ["A1", "A1", "B1"]})) == "context_answer_schema_invalid"
