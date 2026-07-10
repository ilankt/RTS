# AGENTS.md

Guidance for AI coding agents working with this RTS game codebase.

**Read [CLAUDE.md](CLAUDE.md) — it is the maintained agent guide** (quick
start, architecture overview, AI design, debug keys, configuration, known
gaps). This file intentionally defers to it so there is a single source of
truth; an earlier standalone version of this document drifted badly out of
date (it described a pathfinding grid and an AI architecture that were
replaced in 2026).

The active roadmap and working checklist is
**[MASTER_PLAN.md](MASTER_PLAN.md)** — tick items there as they land, and do
not maintain a separate changelog (use `git log`).

Quick facts that agents most often need:

```bash
python main.py                    # run the game (menu)
python main.py --spectate         # watch 4 AIs fight, windowed
python -m pytest tests/ -q        # test suite
python tools/benchmark_ai_spectator.py --seconds 120 --speed 5   # perf gate
python tools/balance_sim.py --matches 20 --players 2             # balance sim
```

- Pathfinding: Jump Point Search over a 20 px square nav grid with
  incremental blocker updates and a cross-frame request queue; group moves
  use flow fields (`systems/flow_field.py`).
- AI: utility AI (`systems/ai/utility/`) reading a per-tick `GoalContext`
  blackboard — goals/brains must not rescan `game.units`/`game.buildings`
  (enforced by `tests/test_ai_contract.py`).
- Combat cadence, movement, and economy all run on game time
  (`delta_time`), never wall-clock time.
