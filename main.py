"""Command-line interface for the Mini Answer Evaluator.

Interactive:       python main.py
Non-interactive:   python main.py -q "Question" -a "Answer" [--rubric ID] [--no-blind] [--json]
Answer from file:  python main.py -q "Question" --answer-file answer.txt
"""

import argparse
import json
import os
import sys

from evaluator_logic import (
    RubricError,
    load_rubrics,
    run_evaluation,
    validate_inputs,
)

WIDTH = 60
_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text, code):
    return f"\033[{code}m{text}\033[0m" if _COLOR else str(text)


def bold(t): return _c(t, "1")
def dim(t): return _c(t, "2")
def red(t): return _c(t, "31")
def green(t): return _c(t, "32")
def yellow(t): return _c(t, "33")


def score_colour(pct, text):
    if pct is None:
        return red(text)
    return green(text) if pct >= 70 else yellow(text) if pct >= 40 else red(text)


def rule(char="─"):
    print(dim(char * WIDTH))


def bar(awarded, maximum, width=20):
    filled = round(width * awarded / maximum) if maximum else 0
    return "█" * filled + dim("░" * (width - filled))


def wrap(text, indent=4):
    import textwrap
    return textwrap.fill(text, width=WIDTH, initial_indent=" " * indent, subsequent_indent=" " * indent)


def read_multiline(label):
    """Read input until a blank line; allows multi-paragraph answers."""
    print(bold(label) + dim("  (finish with an empty line)"))
    lines = []
    while True:
        line = input("  > " if not lines else "  . ")
        if not line.strip():
            if lines:
                break
            print(red("  [!] Input cannot be empty. Please try again."))
            continue
        lines.append(line)
    return "\n".join(lines)


def print_rubric(rubric, selection):
    print()
    if selection.get("manual"):
        how = "chosen manually"
    elif selection.get("fallback"):
        how = "no subject keywords matched"
    else:
        how = "matched: " + ", ".join(selection["matched"])
    print(f"  {bold('Rubric')} : {rubric['subject']}  {dim('(' + how + ')')}")
    for i, c in enumerate(rubric["criteria"], start=1):
        weight = dim(f"({c['weight']})")
        print(f"    {i}. {c['point']} {weight}")


def print_result(title, result):
    print()
    rule("═")
    print(f"  {bold(title.upper())}")
    rule("═")
    if not result["ok"]:
        print("  " + red("Evaluation failed: ") + result["error"])
        if result["justification"]:
            print(wrap(dim(result["justification"])))
        return

    pct = result["percentage"]
    score = f"{result['marks_awarded']} / {result['max_marks']}  ({pct}%)"
    conf = result.get("confidence")
    extra = dim(f"  confidence {round(conf * 100)}%") if conf is not None else ""
    print(f"  Marks : {score_colour(pct, bold(score))}{extra}")

    if result["criteria"]:
        print()
        for c in result["criteria"]:
            pts = f"{c['marks_awarded']}/{c['max_marks']}"
            print(f"  {bar(c['marks_awarded'], c['max_marks'], 10)} {pts:>5}  {c['point']}")
            if c["comment"]:
                print(wrap(dim(c["comment"]), indent=19))
    print()
    print(f"  {bold('Feedback')}")
    print(wrap(result["feedback"]))
    print(f"  {bold('Justification')}")
    print(wrap(result["justification"]))


def print_comparison(guided, blind, comparison):
    print()
    rule("═")
    print(f"  {bold('COMPARISON')}")
    rule("═")
    if not comparison["available"]:
        print("  " + yellow(comparison["observation"]))
    else:
        m = guided["max_marks"]
        print(f"  With rubric : {bar(guided['marks_awarded'], m)} {guided['marks_awarded']}/{m}")
        print(f"  Blind       : {bar(blind['marks_awarded'], m)} {blind['marks_awarded']}/{m}")
        d = comparison["difference"]
        print(f"  Difference  : {d:+d} mark(s). {comparison['observation']} "
              f"{dim('(' + comparison['agreement'] + ' agreement)')}")
    rule("═")
    print()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Evaluate a student's answer with and without a rubric.")
    p.add_argument("-q", "--question", help="Exam question text.")
    p.add_argument("-a", "--answer", help="Student's answer text.")
    p.add_argument("--answer-file", help="Read the student's answer from a file ('-' for stdin).")
    p.add_argument("-r", "--rubric", help="Force a rubric by id instead of auto-detecting.")
    p.add_argument("--list-rubrics", action="store_true", help="List available rubrics and exit.")
    p.add_argument("--no-blind", action="store_true", help="Skip the blind (no-rubric) evaluation.")
    p.add_argument("--json", action="store_true", help="Print the raw result as JSON.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        rubrics = load_rubrics()
    except RubricError as exc:
        print(red(f"[ERROR] {exc}"), file=sys.stderr)
        return 1

    if args.list_rubrics:
        for r in rubrics:
            print(f"{r['id']:<22} {r['subject']} ({r['max_marks']} marks)")
        return 0

    interactive = not args.question
    if interactive:
        print()
        rule("═")
        print(f"  {bold('Mini Answer Evaluator')}")
        rule("═")
        print()
        question = read_multiline("Question")
        print()
        answer = read_multiline("Student's answer")
    else:
        question = args.question
        if args.answer_file:
            with (sys.stdin if args.answer_file == "-" else open(args.answer_file, encoding="utf-8")) as fh:
                answer = fh.read()
        else:
            answer = args.answer or ""

    errors = validate_inputs(question, answer)
    if errors:
        for e in errors:
            print(red(f"[ERROR] {e}"), file=sys.stderr)
        return 2

    if not args.json:
        print(dim("\n  Evaluating" + (" (guided + blind in parallel)" if not args.no_blind else "") + "…"))

    try:
        result = run_evaluation(question, answer, rubrics, rubric_id=args.rubric, include_blind=not args.no_blind)
    except ValueError as exc:
        print(red(f"[ERROR] {exc}"), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_rubric(result["rubric"], result["selection"])
        print_result("With rubric", result["guided"])
        if result["blind"]:
            print_result("Blind (no rubric)", result["blind"])
            print_comparison(result["guided"], result["blind"], result["comparison"])
        else:
            print()

    return 0 if result["guided"]["ok"] else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\n\nExiting evaluator. Goodbye.")
        sys.exit(130)
