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

### 3. Run the evaluator

```bash
python main.py
```

Follow the prompts to enter a question and a student's answer. The tool will select a rubric, evaluate the answer twice, and display a comparison.

---

## Approach

### Rubric Retrieval

The question text is lowercased and tokenised by splitting on whitespace and punctuation. Each token is then checked against each rubric's keyword list:

- **Single-word keywords** (e.g. `"force"`, `"integrate"`) are matched against the set of tokens.
- **Multi-word keywords** (e.g. `"show that"`, `"figure of speech"`) are matched via substring search against the full lowered question text.

The rubric with the most keyword hits wins. If two rubrics tie, the one appearing first in `rubrics.json` is selected. If no rubric scores above zero, the `fallback_general` rubric is used.

This approach is **deterministic and fast**, no embedding model or vector database is required. It works well for the constrained domain of school-level subjects where questions contain distinctive vocabulary.

### Prompt Design

The prompt is split into two parts:

- **System prompt**, fixed instructions that tell the system to behave as an examiner, grade only on what the student wrote, and return a strict JSON object with four keys (`marks_awarded`, `max_marks`, `feedback`, `justification`). The system prompt never changes between evaluations.
- **User prompt**, built dynamically and includes the question, student answer, and (optionally) the rubric criteria. This separation keeps the behavioural instructions stable while varying the task.

**Temperature = 0.2** is chosen for consistency. Grading should be reproducible; high temperature introduces randomness, the same answer could get 6/10 one time and 8/10 another. A small amount of temperature (0.2 rather than 0.0) avoids degenerate decoding issues while keeping output stable.

**JSON-only output** is enforced in the system prompt. As a defensive measure, the code strips markdown code fences (`` ```json `` / `` ``` ``) before parsing. If parsing still fails, a safe fallback dict is returned that includes the first 300 characters of the raw response for debugging.

### Bonus: Guided vs Blind

The evaluator runs two passes:

| Mode | Prompt includes rubric? | What it tests |
|------|------------------------|---------------|
| **Guided** | Yes, criteria + weights + grading instructions | Whether the student's answer meets the specific assessment criteria |
| **Blind** | No, only max marks and a general quality instruction | How general world knowledge rates the answer |

The delta between the two scores reveals how much the rubric changes the outcome. A rubric-guided evaluation is typically more **consistent** and **criterion-specific**, while a blind evaluation reflects the LLM's broader sense of quality. When both agree, you can be more confident in the mark. When they diverge, the rubric criteria likely highlight gaps (or award credit for details) that general evaluation would miss.

---

## The Evaluation Prompt

### System Prompt (always sent)

```
You are a strict but fair academic examiner. Your job is to evaluate a student's
answer to an exam question.

Rules:
- Base your evaluation ONLY on what the student has written. Do not award marks
  for information that is implied but not stated.
- Respond with ONLY a valid JSON object. No explanation before or after it.
- Do not include markdown code fences or any prose outside the JSON.
- The JSON must have exactly these four keys:
    "marks_awarded" : integer between 0 and max_marks (inclusive)
    "max_marks"     : integer (copy from the rubric)
    "feedback"      : 2-4 sentences telling the student what to improve
    "justification" : 1-3 sentences citing specific parts of the answer that
                      drove your scoring decision
```

### Variant 1, `use_rubric=True`

```
Question: {question}

Student's answer: {answer}

Rubric, {rubric['subject']} (max {rubric['max_marks']} marks):
  1. {criteria[0].point} ({criteria[0].weight} marks)
  2. {criteria[1].point} ({criteria[1].weight} marks)
  ...

Grading instruction: {rubric['instructions']}

Evaluate the answer against each criterion above. Award partial marks where
the student has partially satisfied a criterion.
```

### Variant 2, `use_rubric=False`

```
Question: {question}

Student's answer: {answer}

Maximum marks available: {rubric['max_marks']}

Evaluate the answer on its general quality, accuracy, and completeness.
Do not apply any specific rubric.
```

---

## Improvements I Would Make

1. **Semantic retrieval**, Replace keyword matching with sentence embeddings (e.g. using `text-embedding-004`) so that questions like *"What happens when light bends?"* match the physics rubric even without an exact keyword hit.

2. **Chain-of-thought grading**, Ask the system to reason through each criterion before assigning marks (e.g. produce a per-criterion breakdown first, then sum). This improves transparency and often improves scoring accuracy.

3. **Teacher override + feedback loop**, Allow a teacher to review and adjust marks. Store corrections in a log that can be used to fine-tune prompts or behaviour over time.

4. **Multi-model ensemble**, Run the evaluation through two different models and average the scores. This reduces variance and catches model-specific biases.

5. **Confidence score in output**, Ask the system to rate its own certainty (e.g. 0.0-1.0) per criterion. Low-confidence marks can be flagged for human review, combining efficiency with accuracy.
