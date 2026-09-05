# Clubman prototype

The approved style is **Outlined cartoon (option 1)**, now implemented for both clubman and worker. The active renderer, editable models and rebuild instructions are in `../outlined_units/README.md`.

`preview.html`, `walk.gif`, `clubman.blend`, and the game sprite sheets show the approved style. `render.py` forwards to the active outlined renderer; `pack.py` refreshes the clubman gallery from those renders. `options/` retains the three original style studies.

Launch the root's `Play Clubman Prototype.cmd` or run `python art/clubman/play.py` for immediate gameplay with six clubmen and three workers. Press 1 for clubmen or 2 for workers. The normal game entry point also uses the new artwork.

This work lives in the separate `codex/clubman-8-directions` worktree. The original `D:/Dev/RTS` main checkout is unchanged. Unit IDs and combat/economy statistics are preserved; factions and age progression are future work.
