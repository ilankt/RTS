"""Enforce the AI blackboard contract (MASTER_PLAN Phase 4 / §3C).

Goals and sub-brains must read the per-tick GoalContext snapshot, never
rescan game.units / game.buildings / game.resources directly. This test greps
the source so a regression fails loudly in CI rather than silently costing a
full world scan per goal per tick.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Files under the contract. context.py is the one place allowed to scan.
CONTRACT_FILES = [
    "systems/ai/utility/goals/economy.py",
    "systems/ai/utility/goals/military.py",
    "systems/ai/utility/goals/tactical.py",
    "systems/ai/worker_brain.py",
    "systems/ai/military_brain.py",
    "systems/ai/building_placer.py",
    "systems/ai/economy_helpers.py",
]

FORBIDDEN = re.compile(r"game\.(units|buildings|resources|construction_sites)\b")

# economy_helpers keeps one explicitly game-level helper for non-AI callers.
ALLOWED_CONTEXT = {
    "systems/ai/economy_helpers.py": ["def find_nearest_dropoff("],
}


def test_goals_and_brains_do_not_rescan_world_lists():
    violations = []
    for rel_path in CONTRACT_FILES:
        path = os.path.join(ROOT, rel_path)
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        allowed_marker = ALLOWED_CONTEXT.get(rel_path)
        in_allowed_function = False
        for line_number, line in enumerate(source.splitlines(), 1):
            if allowed_marker:
                if any(marker in line for marker in allowed_marker):
                    in_allowed_function = True
                elif in_allowed_function and line.startswith("def "):
                    in_allowed_function = False
            if in_allowed_function:
                continue
            if FORBIDDEN.search(line):
                violations.append(f"{rel_path}:{line_number}: {line.strip()}")
    assert not violations, (
        "AI goals/brains must read the GoalContext blackboard, not rescan world lists:\n"
        + "\n".join(violations)
    )
