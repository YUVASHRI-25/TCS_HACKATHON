import pytest

from trace.domain.guardrails.policy import GuardrailViolation, assert_clean, banned_terms_in, scrub
from trace.domain.scoring.score import ScoreInputs, ScoringConfig, SignalInput, counterfactuals, opens_case, score
from trace.domain.whatif.recompute import next_best_actions, recompute
from trace.intelligence.graph_analytics.networks import group
from trace.domain.model.findings import MODEL, Finding

CFG = ScoringConfig(weights={"a": 25, "b": 20, "c": 15}, ml_weights={"m1": 20, "m2": 20},
                    penalties={"PAYROLL": 30}, bonus_per_extra_signal_type=5, ml_cap=20, min_types=2,
                    tier_high=70, tier_medium=40)


def s(x, *e):
    return SignalInput(x, tuple(e))


def test_score_formula_bonus_and_tier():
    b = score(ScoreInputs({"a": s(1, "E01"), "b": s(1, "E02"), "c": s(1, "E03")}), CFG)
    assert b.total == 25 + 20 + 15 + 5 and b.tier == "MEDIUM" and b.bonus == 5


def test_ml_signals_are_capped_at_20_combined():
    b = score(ScoreInputs({"a": s(1)}, ml_signals={"m1": s(1), "m2": s(1)}), CFG)
    assert b.ml_raw_total == 40 and b.ml_capped_total == 20 and b.total == 45


def test_ml_alone_never_opens_a_case():
    inputs = ScoreInputs({}, ml_signals={"m1": s(1), "m2": s(1)})
    assert not opens_case(inputs, CFG)
    f = Finding("iso", ("account:A",), (), 1.0, {}, "", source=MODEL)
    kept, dropped, rep = group([f], set(), {"iso": "model"}, 50, 2)
    assert kept == [] and rep.dropped_model_only == 1


def test_one_deterministic_type_plus_ml_does_not_open_case():
    fs = [Finding("a", ("account:A",), (), 1.0, {}, ""), Finding("iso", ("account:A",), (), 1.0, {}, "", source=MODEL)]
    kept, _, _ = group(fs, set(), {"a": "risk", "iso": "model"}, 50, 2)
    assert kept == []


def test_penalty_reduces_score_and_counterfactual_finds_minimal_set():
    inputs = ScoreInputs({"a": s(1), "b": s(1), "c": s(1)}, alternative_fits={"PAYROLL": 0.5})
    b = score(inputs, CFG)
    assert b.total == 65 - 15 and b.penalties[0].points == -15
    high = ScoreInputs({"a": s(1), "b": s(1), "c": s(1)}, ml_signals={"m1": s(1)})
    assert score(high, CFG).tier == "HIGH"
    minimal = [c for c in counterfactuals(high, CFG) if c.minimal_tier_change]
    assert len(minimal) == 1 and len(minimal[0].removed) == 1 and minimal[0].tier != "HIGH"


def test_unknown_signal_weight_is_an_error_not_a_default():
    with pytest.raises(KeyError):
        score(ScoreInputs({"zzz": s(1)}), CFG)


def test_whatif_recompute_and_next_best_actions():
    facts = {"payroll_ok": {"label": "x", "on_confirmed": {"set_alternative_fit": {"PAYROLL": 1.0}},
                            "on_refuted": {"set_alternative_fit": {"PAYROLL": 0.0}}, "effort_minutes": None},
             "drop_a": {"label": "y", "on_confirmed": {"remove_signal": ["a"]}, "on_refuted": {}, "effort_minutes": 10}}
    inputs = ScoreInputs({"a": s(1), "b": s(1)})
    r = recompute(inputs, {"payroll_ok": "confirmed"}, facts, CFG)
    assert r["score"] == 45 - 30 and r["changes"][0]["target"] == "PAYROLL"
    nba = next_best_actions(inputs, {}, facts, CFG)
    assert {a["fact"] for a in nba} == {"payroll_ok", "drop_a"} and nba[0]["shift_per_minute"] is not None


def test_banned_words_filter():
    assert banned_terms_in("The holder is GUILTY and a Fraudster.") == ["fraudster", "guilty"]
    assert banned_terms_in("This is confirmed fraud") == ["confirmed fraud"]
    assert banned_terms_in("requires human investigation") == []
    with pytest.raises(GuardrailViolation):
        assert_clean("criminals moved money")
    text, removed = scrub("Funds moved quickly. The launderer is X. Review KYC.")
    assert "launderer" not in text and len(removed) == 1
