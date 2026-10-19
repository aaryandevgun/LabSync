"""Write the eval suites as JSONL (`python3 -m evals.build`). Tests fail if the files drift."""
import json
import os

from . import intake_cases, negotiation_cases, optimizer_cases

HERE = os.path.dirname(os.path.abspath(__file__))


def rendered():
    suites = {"intake": intake_cases.CASES, "negotiation": negotiation_cases.cases(),
              "optimizer": optimizer_cases.cases()}
    return {name + ".jsonl": "".join(json.dumps(c, sort_keys=True) + "\n" for c in rows) for name, rows in suites.items()}


def main():
    for name, text in rendered().items():
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote evals/%s (%d cases)" % (name, text.count("\n")))


if __name__ == "__main__":
    main()
