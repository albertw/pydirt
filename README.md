# pydirt — a Python port of DIRT 3.1

pydirt is a Python/asyncio port of DIRT 3.1, a multi-user dungeon descended 
from AberMUD. It plays the same game from the same data files as the C 
original — same zones, verb table, emotes — with a modern engine.

## Running

No build step, no third-party dependencies — Python 3.10+ is all it takes.

```bash
python -m pydirt.server                 # listens on port 4000
python -m pydirt.server --port 6715     # original DIRT port
python -m pydirt.server --data-dir data # data dir (this is the default)
```

Then connect: `telnet localhost 6715`. First name entered creates a new
character; the game starts at the village church.

## Commands

Movement: `north/south/east/west/up/down` (or `n/s/e/w/u/d`) ·
`look` (`l`), `examine` (`exa`), `exits` ·
`get`, `drop`, `put X in Y`, `get X from Y`, `give X to Y` ·
`wear`, `remove`, `wield`, `inventory` (`i`) ·
`open`, `close`, `eat`/`drink` ·
`say`, `tell`, `shout`, `who`, `score`, `help`, `quit` ·
plus 101 socials (`bow`, `cuddle`, ...) with prefix matching.

## Layout

- `pydirt/` — the server (one module per C counterpart; each module's
  docstring names its C equivalent)
- `data/` — the original DIRT 3.1 data files, read directly
- `tests/` — `python -m pytest tests`
- `doc/` — architecture notes, slides, historical C changelogs

Player characters are stored per-installation in `data/players/` and are
not committed. Dying disconnects you: score halved, gear dropped where you
fell, back home on your next login — as in the original.

## Scope

The port implements the mortal game. Wizard/admin verbs, spells, puzzle
triggers, and the light/darkness system are not yet implemented.