import sys
from evaluator_logic import load_rubrics, get_best_rubric, evaluate_answer

SEPARATOR = "=" * 45

def print_banner():
    print()
    print("=" * 49)
    print("   Mini Answer Evaluator")
    print("=" * 49)
    print()


def prompt_non_blank(label):
    while True:
        value = input(label).strip()
        if value:
            return value
        print("  [!] Input cannot be empty. Please try again.\n")


def print_rubric_criteria(rubric):
    for i, c in enumerate(rubric["criteria"], start=1):
        print(f"  {i}. {c['point']}  ({c['weight']} marks)")


def print_result(title, result):
    print()
    print(SEPARATOR)
    print(f"  EVALUATION RESULT ({title})")
    print(SEPARATOR)
    print(f"  Marks awarded : {result['marks_awarded']} / {result['max_marks']}")
    print(f"  Feedback      : {result['feedback']}")
    print(f"  Justification : {result['justification']}")
    print(SEPARATOR)


def print_comparison(guided, blind):
    g = guided["marks_awarded"]
    b = blind["marks_awarded"]
    diff = g - b

    if diff > 0:
        observation = "Rubric increased the score"
    elif diff < 0:
        observation = "Rubric decreased the score"
    else:
        observation = "Both evaluations agreed"

    max_m = guided["max_marks"]

    print()
    print(SEPARATOR)
    print("  COMPARISON SUMMARY")
    print(SEPARATOR)
    print(f"  With rubric : {g} / {max_m}")
    print(f"  Without     : {b} / {max_m}")
    print(f"  Difference  : {abs(diff)} mark(s), {observation}")
    print(SEPARATOR)
    print()

def main():
    print_banner()
    rubrics = load_rubrics()
    question = prompt_non_blank("Enter the question: ")
    print()
    answer = prompt_non_blank("Enter the student's answer: ")
    print()
    rubric = get_best_rubric(question, rubrics)
    print(f"\n  Rubric selected : {rubric['subject']}")
    print("  Criteria:\n")
    print_rubric_criteria(rubric)
    print("\n  Evaluating with rubric...")
    guided_result = evaluate_answer(question, answer, rubric, use_rubric=True)
    print_result("with rubric", guided_result)
    print("  Evaluating without rubric (blind)...")
    blind_result = evaluate_answer(question, answer, rubric, use_rubric=False)
    print_result("without rubric, blind", blind_result)
    print_comparison(guided_result, blind_result)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting evaluator. Goodbye.")
