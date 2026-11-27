import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402


def gen(system, user, schema):
    if "Rubric," in user:
        return json.dumps({
            "criteria": [{"index": i, "marks_awarded": 1, "comment": f"c{i}"} for i in range(1, 6)],
            "marks_awarded": 5, "max_marks": 10, "feedback": "Add units.", "justification": "Formula ok.",
            "confidence": 0.8,
        })
    return json.dumps({"criteria": [], "marks_awarded": 6, "max_marks": 10,
                       "feedback": "Good.", "justification": "Mostly right."})


@pytest.fixture()
def client():
    return create_app(generate=gen).test_client()


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Mini Answer Evaluator" in r.data


def test_rubrics(client):
    data = client.get("/api/rubrics").get_json()
    assert {r["id"] for r in data} >= {"physics_class12", "fallback_general"}


def test_match(client):
    data = client.post("/api/match", json={"question": "Integrate sin x"}).get_json()
    assert data["rubric_id"] == "mathematics_class12"
    assert "integrate" in data["matched"]


def test_evaluate(client):
    r = client.post("/api/evaluate", json={"question": "Define force.", "answer": "A push or pull."})
    assert r.status_code == 200
    data = r.get_json()
    assert data["rubric"]["id"] == "physics_class12"
    assert data["guided"]["marks_awarded"] == 5
    assert len(data["guided"]["criteria"]) == 5
    assert data["blind"]["marks_awarded"] == 6
    assert data["comparison"]["difference"] == -1


@pytest.mark.parametrize("body", [
    {"question": "", "answer": "x"},
    {"question": "q", "answer": "   "},
    {"question": "q", "answer": "a", "rubric_id": "does_not_exist"},
])
def test_evaluate_bad_input(client, body):
    r = client.post("/api/evaluate", json=body)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_evaluate_non_json(client):
    r = client.post("/api/evaluate", data="hello", content_type="text/plain")
    assert r.status_code == 400
