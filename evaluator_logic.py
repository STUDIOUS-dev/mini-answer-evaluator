import json
import os
import re
import google.generativeai as genai

def load_rubrics(filepath="rubrics.json"):

    if not os.path.isabs(filepath):
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            rubrics = json.load(fh)
        return rubrics
    except FileNotFoundError:
        print(f"[ERROR] Rubrics file not found: {filepath}")
        print("Make sure rubrics.json exists in the project root.")
        raise SystemExit(1)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] rubrics.json contains invalid JSON: {exc}")
        raise SystemExit(1)

def get_best_rubric(question_text, rubrics_data):

    lowered_text = question_text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered_text))

    best_rubric = None
    best_score = 0
    fallback = None

    for rubric in rubrics_data:
        if rubric["id"] == "fallback_general":
            fallback = rubric
            continue

        score = 0
        for keyword in rubric["keywords"]:
            if " " in keyword:
                if keyword in lowered_text:
                    score += 1
            else:
                if keyword in tokens:
                    score += 1

        if score > best_score:
            best_score = score
            best_rubric = rubric

    if best_score == 0:
        selected = fallback
        print(f"[rubric] No keyword matches, using fallback_general (score: 0)")
    else:
        selected = best_rubric
        print(f"[rubric] Selected: {selected['id']} (score: {best_score})")

    return selected
SYSTEM_PROMPT = (
    "You are a strict but fair academic examiner. Your job is to evaluate a "
    "student's answer to an exam question.\n"
    "\n"
    "Rules:\n"
    "- Base your evaluation ONLY on what the student has written. Do not award "
    "marks for information that is implied but not stated.\n"
    "- Award partial marks when a student has partially satisfied a criterion. "
    "Do not binary-score — full marks or zero is rarely correct.\n"
    "- If the answer is blank, completely off-topic, or gibberish, award 0 for "
    "marks_awarded and state this clearly in the justification.\n"
    "- Respond with ONLY a valid JSON object. No explanation before or after it.\n"
    "- Do not include markdown code fences or any prose outside the JSON.\n"
    "- The JSON must have exactly these four keys:\n"
    '    "marks_awarded" : whole integer (no decimals) between 0 and max_marks inclusive\n'
    '    "max_marks"     : whole integer — must exactly match the max_marks value given in the question\n'
    '    "feedback"      : 2-4 sentences telling the student specifically what to improve\n'
    '    "justification" : 1-3 sentences citing specific parts of the answer '
    "that drove your scoring decision\n"
    "\n"
    "Output nothing except the JSON object."
)


def _build_user_prompt(question, answer, rubric, use_rubric):

    if use_rubric:
        criteria_lines = []
        for i, criterion in enumerate(rubric["criteria"], start=1):
            criteria_lines.append(
                f"  {i}. {criterion['point']} ({criterion['weight']} marks)"
            )
        criteria_block = "\n".join(criteria_lines)

        return (
            f"Question: {question}\n\n"
            f"Student's answer: {answer}\n\n"
            f"Rubric, {rubric['subject']} (max {rubric['max_marks']} marks):\n"
            f"{criteria_block}\n\n"
            f"Grading instruction: {rubric['instructions']}\n\n"
            "Evaluate the answer against each criterion above. Award partial "
            "marks where the student has partially satisfied a criterion."
        )
    else:
        return (
            f"Question: {question}\n\n"
            f"Student's answer: {answer}\n\n"
            f"Maximum marks available: {rubric['max_marks']}\n\n"
            "Evaluate the answer on its general quality, accuracy, and "
            "completeness. Do not apply any specific rubric."
        )


def evaluate_answer(question, answer, rubric, use_rubric=True):

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "marks_awarded": 0,
            "max_marks": rubric["max_marks"],
            "feedback": "Evaluation failed: GOOGLE_API_KEY environment variable is not set.",
            "justification": "Cannot call the API without a valid API key.",
        }

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest",
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(temperature=0.2),
    )

    user_prompt = _build_user_prompt(question, answer, rubric, use_rubric)

    try:
        response = model.generate_content(user_prompt)
        raw_text = response.text
    except Exception as exc:
        return {
            "marks_awarded": 0,
            "max_marks": rubric["max_marks"],
            "feedback": f"Evaluation failed: API call error, {exc}",
            "justification": "The API returned an error instead of a result.",
        }

    cleaned = raw_text.strip()
    # Strip markdown code fences if the LLM wrapped its output
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "marks_awarded": 0,
            "max_marks": rubric["max_marks"],
            "feedback": "Evaluation failed: LLM returned malformed output.",
            "justification": f"Raw response: {raw_text[:300]}",
        }

    max_m = rubric["max_marks"]
    awarded = result.get("marks_awarded", 0)
    if not isinstance(awarded, (int, float)):
        awarded = 0
    awarded = int(awarded)
    awarded = max(0, min(awarded, max_m))

    result["marks_awarded"] = awarded
    result["max_marks"] = max_m

    result.setdefault("feedback", "No feedback provided.")
    result.setdefault("justification", "No justification provided.")

    return result
