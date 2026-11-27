# Mini Answer Evaluator

A lightweight CLI tool that evaluates student exam answers using subject-specific rubrics. It performs two evaluations: one guided by a rubric and one blind, then compares the results to show how rubric-based grading changes the outcome.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your API key

The evaluator needs an API key. Set it as an environment variable:

**Linux / macOS:**
```bash
export GOOGLE_API_KEY="your-api-key-here"
```

**Windows (PowerShell):**
```powershell
$env:GOOGLE_API_KEY = "your-api-key-here"
```

**Windows (CMD):**
```cmd
set GOOGLE_API_KEY=your-api-key-here
```

You can get a free API key from [Google AI Studio](https://aistudio.google.com/apikey).

### 3. Run it

**Web app (recommended):**

```bash
python app.py
```

Then open http://127.0.0.1:5000. Type or load a sample question/answer; the rubric is auto-detected live as you type (you can override it). Results show both scores, a per-criterion breakdown with comments, the guided-vs-blind difference, and a history of recent evaluations. You can copy a text report or download the JSON. Light and dark themes are supported.

**CLI:**

```bash
python main.py                                   # interactive (multi-line input, end with a blank line)
python main.py -q "Define force." -a "A push or pull."
python main.py -q "Define force." --answer-file answer.txt --rubric physics_class12
python main.py --list-rubrics
python main.py -q "..." -a "..." --no-blind --json
```

Optional environment variables: `GEMINI_MODEL` (default `gemini-2.5-flash`), `PORT` (web app port, default 5000).

### 4. Run the tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a stub model backend, so they need no API key or network access.

---

## Approach

### Rubric Retrieval

The question text is lowercased and tokenised by splitting on whitespace and punctuation. Each token is then checked against each rubric's keyword list:

- **Single-word keywords** (e.g. `"force"`, `"integrate"`) are matched against the set of tokens.
- **Multi-word keywords** (e.g. `"show that"`, `"figure of speech"`) are matched as whole phrases (word-boundary regex) and count double, since they are more specific.
- Simple plural stemming means `"forces"` matches `"force"` and `"vectors"` matches `"vector"`.

The rubric with the highest score wins, and the matched keywords are shown in the UI so you can see why it was chosen. If two rubrics tie, the one appearing first in `rubrics.json` is selected. If no rubric scores above zero, the `fallback_general` rubric is used.

This approach is **deterministic and fast**, no embedding model or vector database is required. It works well for the constrained domain of school-level subjects where questions contain distinctive vocabulary.

### Prompt Design

The prompt is split into two parts:

- **System prompt**, fixed instructions that tell the system to behave as an examiner, grade only on what the student wrote, and return a strict JSON object with four keys (`marks_awarded`, `max_marks`, `feedback`, `justification`). The system prompt never changes between evaluations.
- **User prompt**, built dynamically and includes the question, student answer, and (optionally) the rubric criteria. This separation keeps the behavioural instructions stable while varying the task.

**Temperature = 0.2** is chosen for consistency. Grading should be reproducible; high temperature introduces randomness, the same answer could get 6/10 one time and 8/10 another. A small amount of temperature (0.2 rather than 0.0) avoids degenerate decoding issues while keeping output stable.

**Structured output**: the request uses Gemini's JSON mode with a response schema, so the model must return a valid object. As a second layer of defence the parser still strips markdown fences and extracts the outermost `{...}` block. If parsing fails, the result is marked `ok: false` with an error message; it is **never** reported as a real score of 0, so a broken call can't skew the comparison.

**Per-criterion scoring**: in guided mode the model scores each rubric criterion separately (with a short comment). Each criterion is clamped to its weight, and the total is the sum, so the overall mark always matches the breakdown.

**Reliability**: the two passes (guided and blind) run in parallel. Transient API errors (429/5xx/timeouts) are retried with exponential backoff. Rubrics are validated on load (required fields, unique ids, weights summing to `max_marks`). The student's answer is wrapped in delimiters and the model is told to treat it as data, which guards against answers that try to instruct the grader.

### Bonus: Guided vs Blind

The evaluator runs two passes:

| Mode | Prompt includes rubric? | What it tests |
|------|------------------------|---------------|
| **Guided** | Yes, criteria + weights + grading instructions | Whether the student's answer meets the specific assessment criteria |
| **Blind** | No, only max marks and a general quality instruction | How general world knowledge rates the answer |

The delta between the two scores reveals how much the rubric changes the outcome. A rubric-guided evaluation is typically more **consistent** and **criterion-specific**, while a blind evaluation reflects the LLM's broader sense of quality. When both agree, you can be more confident in the mark. When they diverge, the rubric criteria likely highlight gaps (or award credit for details) that general evaluation would miss.

---

## The Evaluation Prompt

The full prompts live in `evaluator_logic.py` (`SYSTEM_PROMPT`, `RESPONSE_SCHEMA`, `_build_user_prompt`).

- **System prompt** (always sent): examiner role, grade only what is written, partial credit, treat the answer as data, score each criterion before summing, return JSON.
- **Guided user prompt**: the question and answer (in `<question>`/`<answer>` tags), the numbered rubric criteria with weights, and the rubric's grading instruction.
- **Blind user prompt**: the question, the answer and the maximum marks only.

Response shape:

```json
{
  "criteria": [{"index": 1, "marks_awarded": 2, "comment": "..."}],
  "marks_awarded": 7,
  "max_marks": 10,
  "feedback": "...",
  "justification": "...",
  "confidence": 0.8
}
```

## Project structure

```
evaluator_logic.py   core logic: rubric matching, prompts, Gemini call, parsing, comparison
app.py               Flask web app and JSON API (/api/rubrics, /api/match, /api/evaluate, /api/health)
templates/, static/  web frontend (HTML, CSS, vanilla JS, no build step)
main.py              CLI
rubrics.json         rubric definitions
tests/               pytest suite (stubbed model, no API key needed)
```

---

## Improvements I Would Make

1. **Semantic retrieval**, Replace keyword matching with sentence embeddings (e.g. using `text-embedding-004`) so that questions like *"What happens when light bends?"* match the physics rubric even without an exact keyword hit.

2. **Teacher override + feedback loop**, Allow a teacher to review and adjust marks. Store corrections in a log that can be used to fine-tune prompts or behaviour over time.

3. **Multi-model ensemble**, Run the evaluation through two different models and average the scores. This reduces variance and catches model-specific biases.

4. **Confidence-based review**, The model now returns an overall confidence (0.0-1.0). Low-confidence marks could be automatically flagged for human review.
