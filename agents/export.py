"""Write the JSON files C3 Code needs (`python3 -m agents.export`):

    agents/schemas/<Name>.json     one JSON Schema per structured output
    agents/<agent>/tools.json      that agent's tool list with descriptions and parameters

The tests fail if these files drift from the Python sources.
"""
import json
import os

from . import specs
from .schemas import SCHEMAS

HERE = specs.HERE


def rendered():
    """{relative path: file text} for every exported file."""
    out = {}
    for name, schema in SCHEMAS.items():
        out[os.path.join("schemas", name + ".json")] = json.dumps(schema, indent=2) + "\n"
    for agent in specs.AGENTS:
        out[os.path.join(agent, "tools.json")] = json.dumps(specs.tool_specs(agent), indent=2) + "\n"
    return out


def main():
    for rel, text in rendered().items():
        path = os.path.join(HERE, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote agents/%s" % rel)


if __name__ == "__main__":
    main()
