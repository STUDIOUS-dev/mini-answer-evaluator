"""Web front end for the Mini Answer Evaluator.

Run with:  python app.py   (then open http://127.0.0.1:5000)
"""

import os

from flask import Flask, jsonify, render_template, request

from evaluator_logic import (
    MAX_ANSWER_CHARS,
    MAX_QUESTION_CHARS,
    RubricError,
    load_rubrics,
    run_evaluation,
    select_rubric,
    validate_inputs,
)


def create_app(generate=None, rubrics_path="rubrics.json"):
    """App factory. ``generate`` overrides the model backend (used in tests)."""
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    rubrics = load_rubrics(rubrics_path)

    def _rubric_summary(r):
        return {
            "id": r["id"],
            "subject": r["subject"],
            "max_marks": r["max_marks"],
            "criteria": r["criteria"],
            "instructions": r["instructions"],
        }

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            max_question=MAX_QUESTION_CHARS,
            max_answer=MAX_ANSWER_CHARS,
        )

    @app.get("/api/health")
    def health():
        has_key = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
        return jsonify({"status": "ok", "api_key_configured": has_key or generate is not None})

    @app.get("/api/rubrics")
    def list_rubrics():
        return jsonify([_rubric_summary(r) for r in rubrics])

    @app.post("/api/match")
    def match():
        data = request.get_json(silent=True) or {}
        question = str(data.get("question", ""))
        sel = select_rubric(question, rubrics)
        return jsonify({
            "rubric_id": sel["rubric"]["id"],
            "subject": sel["rubric"]["subject"],
            "score": sel["score"],
            "matched": sel["matched"],
            "fallback": sel["fallback"],
        })

    @app.post("/api/evaluate")
    def evaluate():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Expected a JSON body."}), 400

        question = str(data.get("question", ""))
        answer = str(data.get("answer", ""))
        rubric_id = data.get("rubric_id") or None
        include_blind = bool(data.get("include_blind", True))

        errors = validate_inputs(question, answer)
        if errors:
            return jsonify({"error": " ".join(errors)}), 400

        try:
            result = run_evaluation(
                question, answer, rubrics,
                rubric_id=rubric_id, include_blind=include_blind, generate=generate,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        result["rubric"] = _rubric_summary(result["rubric"])
        return jsonify(result)

    return app


if __name__ == "__main__":
    try:
        application = create_app()
    except RubricError as exc:
        raise SystemExit(f"[ERROR] {exc}")
    port = int(os.environ.get("PORT", 5000))
    application.run(host="127.0.0.1", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
