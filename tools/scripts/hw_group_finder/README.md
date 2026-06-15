# Universal hardware-group finder

Interactive helper to identify the `HARDWARE_GROUP_*` combination of an unknown
AM32 ESC with a multimeter — for **any** MCU family in `Inc/targets.h`, not just
STM32F051 (the older `tools/scripts/f051_hw_group_finder/` only does F051 and asks
in terms of port names).

Two improvements over the F051-only tool:

1. **You pick the chip and the package first**, and from then on the script talks
   in **physical leg numbers of the two ICs on the board** — the MCU and the
   FD6288 gate driver — instead of bare `PAx`/`PBx` port names. "Прозвоните ногу 19
   на ногу 4" instead of "прозвоните PB1 на LIN1".
2. If the wiring you measure **already matches an existing group** (or
   base-group + comparator-order combo), it tells you so and prints the group
   names, instead of emitting fresh `#define`s — so you don't pile up duplicate
   hardware groups in `targets.h`.

## Run

```bash
cd tools/scripts/hw_group_finder
python3 find_hw_group.py
```

No dependencies (pure Python 3, stdlib only).

## What it asks

1. **Chip** — every MCU family that appears in `Inc/targets.h`. Chips whose
   pinout is in the offline reference (`mcu_pinouts.py`) are marked
   `[распиновка ног загружена]` and get full physical-leg guidance; the rest fall
   back to asking by port name (still works, just less convenient).
2. **Package** — e.g. `LQFP48` (4-in-1) vs `LQFP32`/`QFN32`/`QFN28` (singles).
3. **Driver** — confirm it's a **Fortior FD6288**, then its package
   (`FD6288T` TSSOP-20 or `FD6288Q` QFN-24). The FD6288 is on virtually every
   AM32 ESC; its pinout is hardcoded from the datasheet.
4. **Signal input** — ring the Dshot/PWM pad to the MCU; pick the leg it reaches.
5. **Three half-bridges** — for each one:
   - ring the **low-side gate leg** to the driver `LIN1/LIN2/LIN3` legs to find
     which driver **channel** it is;
   - confirm the **high-side gate leg** rings to that same channel's `HIN`
     (if not, you get an *"АНОМАЛИЯ"* warning — the board is non-standard);
   - trace that channel's **`VS` output** through the BEMF divider resistor and
     back to the MCU feedback leg. The first half-bridge offers **3** candidate
     feedback legs, the second **2**, the third **1** (a confirmation) — the same
     narrowing you'd do by hand.

It then prints either the matching existing group(s), or the minimal new
`#define`s, followed by the usual checklist of things a multimeter can't tell you
(DEAD_TIME, driver inversion, voltage/current dividers, telemetry).

## How it stays correct

- The electrical mapping (input pin, gate pins, BEMF pins per group) is **parsed
  directly from `Inc/targets.h`** at runtime (`targets_parser.py`), so it never
  drifts out of sync with the firmware. Nothing about the groups is hand-copied.
- `python3 find_hw_group.py --selftest` replays every group's own wiring back
  through the matcher and asserts it is re-detected — proving the parser and the
  matcher agree with `targets.h`, with no hand-written fixtures.
- Leg numbers live in `mcu_pinouts.py`, each table tagged with its datasheet
  source.

## Pinout coverage

| Chip | Source | Status |
|------|--------|--------|
| STM32F051 | STM32F0 footprint (confirmed by AT32F421 / GD32E230 datasheets) | legs |
| AT32F421 | AT32F421 datasheet V2.02, Table 5 | legs |
| GD32E230 | GD32E230xx datasheet Rev 2.6, pinout figures | legs |
| AT32F415, STM32F031/G031/G071/G431, STM32L431, CH32V203 | — | port-name fallback |

STM32F051, AT32F421 and GD32E230 are pin-for-pin identical for the legs AM32 uses
(Artery and GigaDevice built the F421/E230 as STM32F0 drop-ins), so one verified
table covers all three.

### Adding a chip

Add one table to `PINOUTS`/`CHIPS` in `mcu_pinouts.py`: `"PA2": 12, ...` for the
legs that chip's groups reference (see `python3 targets_parser.py --pins` for the
exact list per MCU), with a `# datasheet:` provenance comment. No other change is
needed — the chip then shows `[распиновка ног загружена]`.

## Notes / limitations

- Only the **FD6288** driver pinout is hardcoded (as requested — it's the
  near-universal choice). For a different gate driver, map its `LIN/HIN/VS` legs
  yourself from its datasheet.
- A few group configs don't expose three separate BEMF sense pins (e.g. the
  STM32G431 `COMP_OVERRIDE` / `G4_A` shared-comparator layout). Those simply
  produce no matchable mapping and are skipped — they need manual schematic work.
- If the motor spins backwards after flashing, that's **not** a wrong group —
  swap any two motor wires.

## Files

- `find_hw_group.py` — interactive flow, matcher, `--selftest`, `--list`.
- `targets_parser.py` — parses `Inc/targets.h` into the group model (`--dump`,
  `--pins`).
- `mcu_pinouts.py` — FD6288 pinout + per-chip/package MCU leg tables.
