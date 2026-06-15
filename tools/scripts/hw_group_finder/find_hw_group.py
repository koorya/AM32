#!/usr/bin/env python3
"""Universal AM32 hardware-group finder.

Walks you through identifying the HARDWARE_GROUP_* combination of an unknown ESC
using a multimeter, phrased in terms of the physical leg numbers of the two ICs
on the board (the MCU and the FD6288 gate driver) instead of bare port names.

Flow:
  1. pick the MCU chip and package, and confirm the gate driver (FD6288 T/Q);
  2. probe the signal pad to find the input leg;
  3. for each of the three half-bridges: ring the low-side gate leg to the driver
     LIN inputs to find its channel, confirm the high-side leg goes to the same
     channel's HIN (board-anomaly check), then trace that channel's VS output
     through the BEMF divider back to the MCU feedback leg (3 candidate legs for
     the first phase, 2 for the second, 1 confirming the third);
  4. report the matching existing group - or, if the wiring is new, the minimal
     set of #defines to add to Inc/targets.h.

The electrical mapping comes straight from Inc/targets.h (see targets_parser.py),
so the tool stays in sync with the firmware. Pin/leg numbers come from
mcu_pinouts.py. No external dependencies.  Run with --selftest to validate the
parser + matcher against every group in targets.h.
"""

import sys

import mcu_pinouts as P
from targets_parser import parse_targets, parse_target_defs, PHASES


# --------------------------------------------------------------------------- #
# Building full mappings (base group x comparator order) from targets.h        #
# --------------------------------------------------------------------------- #

def _family(name):
    """'F0_A' -> 'F0', 'AT_045' -> 'AT', 'F031_A' -> 'F031'."""
    return name.split("_")[0]


class FullMapping(object):
    """A complete board wiring: input leg + 3 (low,high,sense) couples."""

    def __init__(self, names, mcu, input_pin, couples, base, comp_per_phase):
        self.names = names                 # e.g. ["F0_U", "F0_045"]
        self.mcu = mcu
        self.input = input_pin
        self.couples = couples             # frozenset{(low,high,sense)}
        self.base = base
        self.comp_per_phase = comp_per_phase

    @property
    def key(self):
        return (self.input, self.couples)


def build_full_mappings(groups):
    """Return {mcu: [FullMapping,...]} for every base+comp-order combination."""
    bases = [g for g in groups if g.has_gates]
    comp_blocks = [g for g in groups if g.has_comp and not g.has_gates]

    out = {}
    for base in bases:
        comp_sets = []  # (extra_names, {phase: sense})
        if base.distinct_sense:
            # base already fully specifies its comparator pins (e.g. F0_A, GD_A):
            # it is used on its own, never with an external comp-order block.
            comp_sets.append(([], dict(base.comp)))
        else:
            # base defines only the gate pins (e.g. F0_U, AT_B): it must be paired
            # with a comparator-order block of the same family.
            for cb in comp_blocks:
                if _family(cb.name) == _family(base.name) and cb.distinct_sense:
                    comp_sets.append(([cb.name], dict(cb.comp)))
        for extra_names, comp in comp_sets:
            couples = set()
            ok = True
            for p in PHASES:
                lo, hi = base.gates[p]
                sense = comp.get(p)
                if not sense:
                    ok = False
                    break
                couples.add((lo, hi, sense))
            if not ok or len(couples) != 3:
                continue
            fm = FullMapping([base.name] + extra_names, base.mcu, base.input,
                             frozenset(couples), base, comp)
            out.setdefault(base.mcu, []).append(fm)
    return out


# --------------------------------------------------------------------------- #
# Matching                                                                     #
# --------------------------------------------------------------------------- #

def match_board(board_input, board_couples, mappings):
    """Return list of FullMappings whose wiring equals the measured board."""
    key = (board_input, frozenset(board_couples))
    return [m for m in mappings if m.key == key]


def find_emit(board_input, board_couples, groups, mcu):
    """No exact full mapping matched: describe the minimal new defines.

    Returns (base_name, comp_order_name_or_None, comp_per_phase) or None.
    Prefers a gate-only base (e.g. F0_U) so the suggested comparator order does
    not clash with a comparator order the base already hardcodes.
    """
    board_pairs = {(lo, hi) for (lo, hi, s) in board_couples}
    sense_for_pair = {(lo, hi): s for (lo, hi, s) in board_couples}
    bases = [g for g in groups if g.has_gates and g.mcu == mcu
             and g.input == board_input
             and {tuple(g.gates[p]) for p in PHASES} == board_pairs]
    # gate-only bases first (distinct_sense False sorts before True)
    bases.sort(key=lambda b: b.distinct_sense)
    comp_blocks = [g for g in groups if g.has_comp and not g.has_gates]

    for base in bases:
        comp_per_phase = {p: sense_for_pair.get(tuple(base.gates[p]))
                          for p in PHASES}
        if base.distinct_sense:
            # base hardcodes its comparator pins; only clean if they already
            # match (otherwise keep looking for a gate-only base).
            if all(base.comp.get(p) == comp_per_phase[p] for p in PHASES):
                return (base.name, None, comp_per_phase, True)
            continue
        # gate-only base: reuse a named comparator-order block if one matches,
        # otherwise the order is genuinely new -> explicit PHASE_*_COMP.
        for cb in comp_blocks:
            if _family(cb.name) == _family(base.name) and \
                    all(cb.comp.get(p) == comp_per_phase[p] for p in PHASES):
                return (base.name, cb.name, comp_per_phase, True)
        return (base.name, None, comp_per_phase, True)

    # only inline-comp bases exist for this input (e.g. F0_A/C/E on PA2, or GD32):
    # the comparator order is new and cannot be bolted onto a base that already
    # fixes one -> a brand new base block is needed. Return clean=False so the
    # report says so, referencing the matching base's gate pins to copy.
    if bases:
        base = bases[0]
        comp_per_phase = {p: sense_for_pair.get(tuple(base.gates[p]))
                          for p in PHASES}
        return (base.name, None, comp_per_phase, False)
    return None


# --------------------------------------------------------------------------- #
# Interactive helpers                                                          #
# --------------------------------------------------------------------------- #

def ask_choice(prompt, options, render=str):
    """Pick one of options (list). render(opt) -> label. Returns the chosen opt."""
    while True:
        print(prompt)
        for i, opt in enumerate(options, 1):
            print("  %d) %s" % (i, render(opt)))
        raw = input("> ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("Введите номер варианта.\n")


def ask_yes_no(prompt, default=True):
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        raw = input(prompt + suffix).strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes", "д", "да"):
            return True
        if raw in ("n", "no", "н", "нет"):
            return False


def leg(pkg_map, port):
    """Format a port as 'нога 15 (PB1)' using the package map, or just port."""
    if pkg_map and port in pkg_map:
        return "нога %s (%s)" % (pkg_map[port], port)
    return port


# --------------------------------------------------------------------------- #
# The interactive session                                                      #
# --------------------------------------------------------------------------- #

def targets_for_names(names, targets):
    """Board targets that enable exactly the groups in `names`.

    A mapping's `names` are the HARDWARE_GROUP_* suffixes that make up the
    wiring (e.g. ["AT_B", "AT_504"]). Returns every Target whose own group set
    contains all of them, so the user can reuse a ready-made target instead of
    inventing a new one.
    """
    want = set(names)
    return [t for t in targets if want <= t.groups]


def run_interactive(groups, full_mappings, targets):
    print(__doc__.split("\n\n")[0])
    print("=" * 72)

    # --- 1. chip -----------------------------------------------------------
    mcus = sorted({g.mcu for g in groups if g.has_gates and g.mcu},
                  key=lambda m: P.CHIPS.get(m, {}).get("name", m))
    def chip_label(m):
        c = P.chip_for_mcu(m)
        return ("%s  [распиновка ног загружена]" % c["name"]) if c else \
               ("%s  [нет распиновки — спрошу по именам портов]" % m)
    mcu = ask_choice("\nКакой микроконтроллер стоит на плате?", mcus, chip_label)
    chip = P.chip_for_mcu(mcu)

    # --- 2. package --------------------------------------------------------
    pkg_map = None
    if chip:
        pkg = ask_choice("\nВ каком корпусе?", sorted(chip["packages"].keys()))
        pkg_map = chip["packages"][pkg]
        print("(распиновка: %s)" % chip["source"])
    else:
        print("\nРаспиновки этого чипа пока нет в справочнике (mcu_pinouts.py),\n"
              "поэтому ноги буду спрашивать по именам портов (PA2, PB1, ...).")

    # --- 3. driver ---------------------------------------------------------
    print("\n" + "=" * 72)
    if not ask_yes_no("Драйвер полумостов — Fortior FD6288?", True):
        print("Этот скрипт знает распиновку только FD6288. Для другого драйвера\n"
              "найдите соответствия LIN/HIN/VS вручную по его datasheet.")
        return
    drv_pkg = ask_choice("Корпус драйвера FD6288?", list(P.FD6288.keys()))

    def drv(sig):
        return "нога %s (%s)" % (P.fd6288_pin(drv_pkg, sig), sig)

    # --- mappings for this MCU --------------------------------------------
    mappings = full_mappings.get(mcu, [])
    if not mappings:
        print("\nВ targets.h нет групп с полной BEMF-распиновкой для %s — "
              "матчинг невозможен." % mcu)
        return

    # candidate input legs / pins from the base groups
    inputs = sorted({m.input for m in mappings if m.input})
    sense_pins = sorted({s for m in mappings for (_, _, s) in m.couples})

    # --- 4. signal input ---------------------------------------------------
    print("\n" + "=" * 72)
    print("Шаг 1. Сигнальный вход (Dshot/PWM)")
    print("=" * 72)
    board_input = ask_choice(
        "Прозвоните сигнальную площадку до МК. К какой ноге она идёт?",
        inputs, lambda p: leg(pkg_map, p))
    mappings = [m for m in mappings if m.input == board_input]

    # canonical gate-pairs: take the modal base among the filtered mappings
    base = _modal_base(mappings)
    pairs = [tuple(base.gates[p]) for p in PHASES]

    # --- 5. per half-bridge ------------------------------------------------
    print("\n" + "=" * 72)
    print("Шаг 2. Три полумоста: канал драйвера и BEMF-делитель")
    print("=" * 72)
    print("Для каждой пары затворов: сначала нижнее плечо -> вход LIN драйвера\n"
          "(определяем номер канала), потом проверяем верхнее плечо -> HIN того\n"
          "же канала, потом выход VS этого канала -> делитель -> нога МК.\n")

    used_sense = []
    board_couples = []
    for idx, (lo, hi) in enumerate(pairs, 1):
        print("-" * 72)
        print("Полумост %d:  нижнее плечо %s,  верхнее плечо %s"
              % (idx, leg(pkg_map, lo), leg(pkg_map, hi)))

        # low arm -> channel
        ch = ask_choice(
            "Нижнее плечо %s звонится на какой вход драйвера?" % leg(pkg_map, lo),
            [1, 2, 3], lambda n: "LIN%d (%s)" % (n, drv("LIN%d" % n)))

        # high arm anomaly check
        if not ask_yes_no("Проверка: верхнее плечо %s звонится на HIN%d (%s)?"
                          % (leg(pkg_map, hi), ch, drv("HIN%d" % ch)), True):
            print("  !! АНОМАЛИЯ: верхнее плечо не на HIN%d того же канала.\n"
                  "     Плата нестандартная — дальше можно, но проверьте схему."
                  % ch)

        # BEMF: VS of this channel -> divider -> sense leg
        candidates = [s for s in sense_pins if s not in used_sense]
        if len(candidates) == 1:
            sense = candidates[0]
            print("BEMF: выход %s -> делитель -> остаётся одна нога: %s "
                  "(подтвердите прозвонкой)." % (drv("VS%d" % ch),
                                                 leg(pkg_map, sense)))
        else:
            sense = ask_choice(
                "BEMF: выход %s -> через резистор делителя -> обратная сторона "
                "резистора\nидёт на какую ногу МК?" % drv("VS%d" % ch),
                candidates, lambda p: leg(pkg_map, p))
        used_sense.append(sense)
        board_couples.append((lo, hi, sense))
        print()

    # --- 6. resolve --------------------------------------------------------
    _report(board_input, board_couples, groups, mcu, mappings, targets)


def _modal_base(mappings):
    counts = {}
    for m in mappings:
        k = tuple(tuple(m.base.gates[p]) for p in PHASES)
        counts.setdefault(k, []).append(m.base)
    best = max(counts.values(), key=len)
    return best[0]


def _report(board_input, board_couples, groups, mcu, mappings, targets):
    print("=" * 72)
    print("Результат")
    print("=" * 72)
    matches = match_board(board_input, board_couples, mappings)
    if matches:
        seen = set()
        matched_targets = []   # preserve order, dedupe by target name
        seen_targets = set()
        print("Такая распиновка УЖЕ есть в targets.h — новые дефайны не нужны.")
        print("Подходящие группы:")
        for m in matches:
            label = " + ".join("HARDWARE_GROUP_" + n for n in m.names)
            if label not in seen:
                seen.add(label)
                print("  %s" % label)
            for t in targets_for_names(m.names, targets):
                if t.name not in seen_targets:
                    seen_targets.add(t.name)
                    matched_targets.append(t)
        if matched_targets:
            print("\nГотовые таргеты с такой распиновкой (можно прошивать как есть):")
            for t in matched_targets:
                fw = ' — "%s"' % t.firmware_name.strip() if t.firmware_name else ""
                print("  %s%s" % (t.name, fw))
            print("\nЕсли ваша плата — один из них, отдельный таргет не нужен.")
        else:
            print("\nГруппы есть, но ни один таргет их пока не использует.")
        print("\nИначе используйте эту комбинацию групп в новом таргете "
              "(FILE_NAME/FIRMWARE_NAME свои), чтобы не плодить дубли.")
    else:
        emit = find_emit(board_input, board_couples, groups, mcu)
        print("Точного совпадения нет — это новая комбинация.\n")
        if emit and emit[3]:
            base_name, comp_name, comp_per_phase, _ = emit
            print("Добавьте в новый таргет в targets.h:")
            print("  #define HARDWARE_GROUP_%s" % base_name)
            if comp_name:
                print("  #define HARDWARE_GROUP_%s" % comp_name)
            else:
                print("  // новый порядок компараторов под эту плату:")
                for p in PHASES:
                    print("  #define PHASE_%s_COMP   /* %s */"
                          % (p, comp_per_phase[p]))
        elif emit:
            base_name, _, comp_per_phase, _ = emit
            print("Это новый порядок компараторов для входа %s. Базовая группа\n"
                  "HARDWARE_GROUP_%s уже жёстко задаёт свой порядок, поэтому нужна\n"
                  "НОВАЯ базовая группа: скопируйте затворные #define из %s и задайте"
                  % (board_input, base_name, base_name))
            print("свой порядок компараторов:")
            for p in PHASES:
                print("  #define PHASE_%s_COMP   /* %s */" % (p, comp_per_phase[p]))
        else:
            print("  (не удалось подобрать базовую группу под измеренные затворы —")
            print("   распиновка затворов нестандартная, разберите схему вручную)")
        print("\nИзмеренные пары (низ, верх -> BEMF):")
        for (lo, hi, s) in board_couples:
            print("  %s / %s -> %s" % (lo, hi, s))

    _checklist()


def _checklist():
    print("\nЧто ещё нужно задать в таргете отдельно (мультиметром не берётся):")
    print("  - DEAD_TIME — по драйверу/опытно")
    print("  - USE_INVERTED_LOW/HIGH, USE_OPEN_DRAIN_* — если драйвер инвертирующий")
    print("  - TARGET_VOLTAGE_DIVIDER, MILLIVOLT_PER_AMP, CURRENT_OFFSET — по резисторам")
    print("  - USE_SERIAL_TELEMETRY / USE_PA14_TELEMETRY — если есть телеметрийный пад")
    print("  - реверс мотора правится перестановкой двух фазных проводов, не группой")


# --------------------------------------------------------------------------- #
# Self-test: replay every full mapping through the matcher                     #
# --------------------------------------------------------------------------- #

def selftest(groups, full_mappings):
    total = 0
    fails = 0
    for mcu, mappings in full_mappings.items():
        for m in mappings:
            total += 1
            got = match_board(m.input, list(m.couples), mappings)
            if m not in got:
                fails += 1
                print("FAIL: %s (%s) not re-detected" % ("+".join(m.names), mcu))
                continue
            # if this mapping is unique, emit-path must also reconstruct it
            if len(got) == 1:
                emit = find_emit(m.input, list(m.couples), groups, mcu)
                # for a real group a base must always be reconstructable.
                if emit is None:
                    fails += 1
                    print("FAIL emit: %s base not reconstructable" % "+".join(m.names))
    uniq = sum(len(v) for v in full_mappings.values())
    print("selftest: %d full mappings across %d MCU(s); %d failures"
          % (uniq, len(full_mappings), fails))
    return fails == 0


# --------------------------------------------------------------------------- #

def main():
    groups = parse_targets()
    targets = parse_target_defs()
    full_mappings = build_full_mappings(groups)
    if "--selftest" in sys.argv:
        ok = selftest(groups, full_mappings)
        sys.exit(0 if ok else 1)
    if "--list" in sys.argv:
        for mcu, ms in sorted(full_mappings.items(), key=lambda kv: str(kv[0])):
            print("%s: %d mappings" % (mcu, len(ms)))
        return
    try:
        run_interactive(groups, full_mappings, targets)
    except (KeyboardInterrupt, EOFError):
        print("\nОтменено.")


if __name__ == "__main__":
    main()
