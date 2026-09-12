---
name: rts-balance-audit
description: Run reproducible faction, unit, upgrade and AI balance audits for the RTS project, including paired simulations and low-overhead unattended reporting. Use for requested balance audits and repeat balance batteries, not ordinary gameplay edits.
---

Use the maintained harness in `D:/Dev/RTS/tools/`. Read `CLAUDE.md`, the current report in `feedback/`, and relevant `PLAN_ARCHIVE.md` balance decisions before changing gameplay. Audit findings and uncommitted source are evidence, not proof that fixes have landed.

## Keep model and machine overhead low

- Simulate, aggregate, validate and package with local Python. The simulation itself needs no LLM/API calls. Do not reason over every match, read raw logs repeatedly, or loop through minute-long model polls.
- Default to four below-normal-priority workers on this user's machine; twelve previously caused excessive load. Keep concurrency fixed within comparisons and record it. Reducing workers trades elapsed time for responsiveness, not statistical quality.
- Use `tools/run_audit_pipeline.py` for finite unattended work. It writes `status.json`, per-stage logs, resumable match records and the final report. Inspect one compact status after useful work or at completion. If the user authorizes reporting later, use the app's supported task follow-up, at a sparse interval (e.g. two hours), silent while unchanged, and disable it on completion/failure. Do not claim a notification is arranged until the tool confirms it. Do not leave an active model polling merely to keep the conversation alive.
- Keep summaries small; load individual raw matches only for a specific finding. A skill reduces rediscovery; it cannot guarantee a particular subscription percentage or make reasoning free.

## Run contract

For the established 150-game repeat:

```powershell
python tools/run_audit_pipeline.py --games-per-size 50 --workers 4 --seconds 2400 --normal-controls
```

The pipeline expects the full regression suite already passed in `_gen/audit_after_tests.log`, and current mechanics evidence in `_gen/faction_mechanics_after`. Generate mechanics with `python tools/run_audit_checks.py`. A new audit should use a new output directory and adapt the report's comparison baseline explicitly; the repeat reporter currently targets the September 8 baseline. Never overwrite a historical evidence directory.

- Use the real `Game.update` simulation. 2/4/6 players map to 45/60/70 square map dimensions. Normal difficulty, Stone start, annihilation, 2,400 game-second cap are the established baseline settings.
- Each player count gets an even game count. Pair the same seed/map/seats/personalities with every faction swapped. Half of the seats belong to each faction in every match. Validate equal exposure per seat/personality, not just total counts.
- The 150 schedule uses the first 25 pairs from each baseline size (match IDs shift; join on player count, pair and arm). Before/after compares a package of changes, not the independent effect of each fix.
- Freeze gameplay and observer hashes. Resume only identical manifests; don't silently reuse files from another build. A source mismatch or a failed match requires investigation. Keep incomplete attempts separate; do not replace timeouts with wins or discard inconvenient results.
- The established batch step is 1/12 game second (1/60 input, speed 5). Include stationary cadence and lane checks at 1/60. `--normal-controls` adds six full games (one mirrored pair per map size), clearly outside the 150 primary games. Native wall-clock pathfinding budgets prevent exact replay guarantees.

## Interpret evidence correctly

- Use whole-pair bootstrap intervals; show resolved and unresolved counts separately. Suppress misleading intervals when resolved evidence is sparse. An interval spanning 50% does not establish equivalence, especially with high timeout rates.
- Inspect all unit lines and all technologies: paid unlock/recruitment, prerequisite chains, effects on existing and new units, actual hit-level improvement, natural AI access/affordability/selection, and meaningful support metrics. Healers need healing metrics; workers need economy metrics; siege needs structure damage.
- Count actual HP removed, excluding overkill, retaining the original target when a killing hit clears `current_target`. Separate worker/military casualties and foundations/completed buildings. Upgrade adoption versus wins is confounded by survival and wealth.
- Use current display names: **Ballista / Heavy Ballista**. `ram` is a legacy internal ID retained for compatibility. The sword/archer line IDs also encompass several age variants.
- Correctness before tuning: fractional endpoint truncation can erase first-tier bonuses; cooldown resets can discard overshoot; a health denominator accidentally using current HP makes every building appear healthy. Test combat outcomes, not just larger effective-stat getters.
- Test Axeman's sword-infantry role with normal-step duels and equal starting resource budgets, recording leftover resources and troop counts. Do not call idealized lanes full-game proof. Preserve the distinctions between access problems, AI micro failures and intrinsic unit strength.
- Diagnose large-game stalls over time. Target concentration in one screenshot alone does not establish a navigation bug. Keep tactical focus local, inspect siege objectives and pursuit progress, and respect the GoalContext blackboard contract.

Deliver a compact conclusion plus the generated Markdown report and evidence ZIP. Update `MASTER_PLAN.md` as findings land. Clearly identify remaining uncertainty and whether the batch is actually complete.
