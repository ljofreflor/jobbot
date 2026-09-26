"""Knowledge compilation contract — System 2 vibecode → System 1 feature."""

from jobbot.ops.compile import COMPRESS_CONTRACT, PROMOTION_STEPS


def test_compress_contract_states_fast_slow_split() -> None:
    assert "System 2" in COMPRESS_CONTRACT
    assert "System 1" in COMPRESS_CONTRACT
    assert "vibecode" in COMPRESS_CONTRACT


def test_compress_contract_mentions_symptom() -> None:
    assert "symptom" in COMPRESS_CONTRACT


def test_promotion_steps_end_with_triage() -> None:
    assert PROMOTION_STEPS[0] == "capture_symptom_redacted_locally"
    assert PROMOTION_STEPS[-1] == "triage_symptom_resolved"
    assert "call_feature_do_not_rederive" in PROMOTION_STEPS
    assert "optional_llm_inside_via_gateway" in PROMOTION_STEPS
