import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import evaluator_logic as ev  # noqa: E402


@pytest.fixture(scope="module")
def rubrics():
    return ev.load_rubrics()


def fake_generator(payload):
    def gen(system, user, schema):
        return payload if isinstance(payload, str) else json.dumps(payload)
    return gen


# ── Rubric selection ────────────────────────────────────────

@pytest.mark.parametrize("question,expected", [
    ("State Ohm's law and give the SI unit of resistance.", "physics_class12"),
    ("Calculate the net forces acting on the block.", "physics_class12"),  # plural stemmed
    ("Integrate x^2 e^x and hence show that the result holds.", "mathematics_class12"),
    ("Identify the figure of speech in the poem.", "english_class10"),
    ("Who won the 1998 world cup?", "fallback_general"),
])
def test_select_rubric(rubrics, question, expected):
    assert ev.select_rubric(question, rubrics)["rubric"]["id"] == expected


def test_selection_reports_matched_keywords(rubrics):
    sel = ev.select_rubric("Define electric current.", rubrics)
    assert set(sel["matched"]) >= {"define", "electric", "current"}
    assert not sel["fallback"]


def test_multiword_keyword_respects_word_boundaries(rubrics):
    # "show thatched" must not count as "show that"
    ranked = ev.rank_rubrics("show thatched roof", rubrics)
    maths = next(r for r in ranked if r["rubric"]["id"] == "mathematics_class12")
    assert "show that" not in maths["matched"]


def test_get_best_rubric_backcompat(rubrics):
    assert ev.get_best_rubric("Solve the equation", rubrics)["id"] == "mathematics_class12"


def test_rubric_validation_rejects_bad_weights(tmp_path):
    bad = [{"id": "x", "subject": "X", "keywords": [], "max_marks": 10, "instructions": "",
            "criteria": [{"point": "a", "weight": 3}]}]
    path = tmp_path / "r.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ev.RubricError, match="sum to 3"):
        ev.load_rubrics(str(path))


def test_missing_rubrics_file():
    with pytest.raises(ev.RubricError):
        ev.load_rubrics("/nonexistent/rubrics.json")


# ── Evaluation / parsing ────────────────────────────────────

def test_guided_total_is_sum_of_clamped_criteria(rubrics):
    rubric = ev.get_rubric_by_id("physics_class12", rubrics)
    payload = {
        "criteria": [
            {"index": 1, "marks_awarded": 2, "comment": "good"},
            {"index": 2, "marks_awarded": 99, "comment": "over max"},   # clamp to 3
            {"index": 3, "marks_awarded": -4, "comment": "negative"},   # clamp to 0
            {"index": 4, "marks_awarded": 1, "comment": ""},
        ],  # criterion 5 missing -> 0
        "marks_awarded": 10, "max_marks": 7,
        "feedback": "f", "justification": "j", "confidence": 1.7,
    }
    r = ev.evaluate_answer("q", "a", rubric, True, fake_generator(payload))
    assert r["ok"]
    assert [c["marks_awarded"] for c in r["criteria"]] == [2, 3, 0, 1, 0]
    assert r["marks_awarded"] == 6
    assert r["max_marks"] == 10
    assert r["percentage"] == 60.0
    assert r["confidence"] == 1.0


def test_blind_uses_top_level_marks(rubrics):
    rubric = ev.get_rubric_by_id("english_class10", rubrics)
    payload = {"criteria": [], "marks_awarded": 7.6, "max_marks": 10, "feedback": "f", "justification": "j"}
    r = ev.evaluate_answer("q", "a", rubric, False, fake_generator(payload))
    assert r["ok"] and r["marks_awarded"] == 8 and r["criteria"] == []


def test_code_fenced_json_is_parsed(rubrics):
    rubric = rubrics[0]
    raw = "```json\n" + json.dumps({"criteria": [], "marks_awarded": 4, "max_marks": 10,
                                    "feedback": "f", "justification": "j"}) + "\n```"
    r = ev.evaluate_answer("q", "a", rubric, False, fake_generator(raw))
    assert r["ok"] and r["marks_awarded"] == 4


def test_malformed_output_is_failure_not_zero(rubrics):
    r = ev.evaluate_answer("q", "a", rubrics[0], True, fake_generator("not json at all"))
    assert not r["ok"]
    assert r["marks_awarded"] is None
    assert "malformed" in r["error"]


def test_api_exception_is_failure(rubrics):
    def boom(*_):
        raise RuntimeError("quota exceeded")
    r = ev.evaluate_answer("q", "a", rubrics[0], True, boom)
    assert not r["ok"] and "quota exceeded" in r["error"]


def test_missing_api_key(monkeypatch, rubrics):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(ev, "_client", None)
    r = ev.evaluate_answer("q", "a", rubrics[0], True)
    assert not r["ok"] and "API key" in r["error"]


def test_prompt_contains_rubric_only_when_guided(rubrics):
    rubric = rubrics[0]
    guided = ev._build_user_prompt("Q?", "A.", rubric, True)
    blind = ev._build_user_prompt("Q?", "A.", rubric, False)
    assert rubric["criteria"][0]["point"] in guided
    assert rubric["criteria"][0]["point"] not in blind
    assert "<answer>\nA.\n</answer>" in guided


# ── Pipeline ────────────────────────────────────────────────

def test_run_evaluation_and_comparison(rubrics):
    def gen(system, user, schema):
        if "Rubric," in user:
            return json.dumps({"criteria": [{"index": i, "marks_awarded": 1, "comment": ""} for i in range(1, 6)],
                               "marks_awarded": 0, "max_marks": 10, "feedback": "f", "justification": "j"})
        return json.dumps({"criteria": [], "marks_awarded": 8, "max_marks": 10, "feedback": "f", "justification": "j"})

    out = ev.run_evaluation("Define force.", "Force is a push or pull.", rubrics, generate=gen)
    assert out["rubric"]["id"] == "physics_class12"
    assert out["guided"]["marks_awarded"] == 5
    assert out["blind"]["marks_awarded"] == 8
    assert out["comparison"]["difference"] == -3
    assert out["comparison"]["agreement"] == "moderate"


def test_run_evaluation_manual_rubric_and_no_blind(rubrics):
    gen = fake_generator({"criteria": [], "marks_awarded": 5, "max_marks": 10, "feedback": "f", "justification": "j"})
    out = ev.run_evaluation("Define force.", "x", rubrics, rubric_id="english_class10", include_blind=False, generate=gen)
    assert out["rubric"]["id"] == "english_class10"
    assert out["selection"]["manual"] and out["selection"]["suggested_id"] == "physics_class12"
    assert out["blind"] is None and out["comparison"] is None


def test_unknown_rubric_id(rubrics):
    with pytest.raises(ValueError):
        ev.run_evaluation("q", "a", rubrics, rubric_id="nope", generate=fake_generator("{}"))


def test_comparison_unavailable_when_failed(rubrics):
    out = ev.run_evaluation("q", "a", rubrics, generate=fake_generator("garbage"))
    assert out["comparison"]["available"] is False


def test_validate_inputs():
    assert ev.validate_inputs("  ", "a")
    assert ev.validate_inputs("q", "")
    assert ev.validate_inputs("q" * (ev.MAX_QUESTION_CHARS + 1), "a")
    assert ev.validate_inputs("q", "a") == []
