# Adventure: Forge notes

Reference for the Tinkerer `forge` command.

## Forge limit

A character can own at most **3** forged items at once.

- Defined as `FORGE_LIMIT = 3` in `class_abilities.py`. The `forge` command checks it.
- `charsheet.py` has a hardcoded `forged >= 3` in the rebirth code. It is **not** imported
  from `FORGE_LIMIT`, so change both places together.
- When a character is at the limit, `forge` shows `ForgeReplaceView` so they can pick an
  existing forged item to replace.

## What can be forged

Forgeable: normal, rare, epic, legendary, **set**, and ascended (ascended needs 30+ rebirths).

Not forgeable: **forged** and **event** items.

Set pieces were previously blocked and are now allowed. The restriction lived in the four places
below, so re-adding it means changing all of them:

| File | Location | What it does |
| --- | --- | --- |
| `class_abilities.py` | `forge`, `ignored_rarities` | Leaves excluded rarities out of the forgeable list and the "need two forgeable items" check |
| `class_abilities.py` | `get_forge_items`, `ignored_rarities` | Same list, used when the player types an item name |
| `class_abilities.py` | `get_forge_items`, rarity check | Shows "{rarity} items cannot be reforged." for a blocked item |
| `charsheet.py` | forging branch of the backpack builder | Skips blocked rarities so they don't appear in the forge menu |

Forged items are still blocked in all of these.
