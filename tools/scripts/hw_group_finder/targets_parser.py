#!/usr/bin/env python3
"""Parse Inc/targets.h into a normalized model of every HARDWARE_GROUP_*.

This is the single source of truth for the hardware-group finder: instead of
hand-duplicating pin maps, we read them straight out of the firmware so the tool
stays in sync with targets.h automatically.

Each group is reduced to:
  * mcu          - the MCU_* family it belongs to (e.g. "F051")
  * input        - signal-input pin as a port name ("PA2") or None
  * gates        - {phase: (low_pin, high_pin)} as port names ("PB1","PA10")
  * comp         - {phase: sense_pin or None}, the BEMF feedback pin per phase

A group that defines gate pins is a "base" group; a group that only defines the
three PHASE_*_COMP pins is a "comp-order" group (e.g. F0_045). Run with --dump to
inspect the parsed result.
"""

import os
import re

PHASES = ("A", "B", "C")

# Default location of targets.h relative to this script (tools/scripts/hw_group_finder/).
DEFAULT_TARGETS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "Inc", "targets.h")
)


def _pin_name(port_token, pin_token):
    """('GPIOB','LL_GPIO_PIN_1') -> 'PB1'. Returns None if either is missing."""
    if not port_token or not pin_token:
        return None
    m = re.search(r"GPIO([A-F])", port_token)
    # pin number: LL_GPIO_PIN_1 / GPIO_PINS_1 / GPIO_PIN_1 / GPIO_Pin_1
    n = re.search(r"(?:PIN|PINS|Pin)_(\d+)", pin_token)
    if not m or not n:
        return None
    return "P{}{}".format(m.group(1), int(n.group(1)))


def _sense_from_comp(value, comment):
    """Derive the MCU feedback pin from a PHASE_x_COMP value/comment.

    Handles COMP_PAx tokens (F0), '// pax' / '// CMP_PAx' comments (G0/L4/G4/GD),
    and AT32's hex magic numbers (pin only recoverable from the comment).
    Returns 'PA0' etc., or None if not recoverable.
    """
    m = re.search(r"COMP_PA(\d+)", value)
    if m:
        return "PA" + m.group(1)
    if comment:
        m = re.search(r"P([A-F])\s*(\d+)", comment, re.I)
        if m:
            return "P{}{}".format(m.group(1).upper(), int(m.group(2)))
    return None


class Group(object):
    def __init__(self, name):
        self.name = name
        self.mcu = None
        self.input = None
        self.gates = {p: [None, None] for p in PHASES}   # [low, high]
        self.comp = {p: None for p in PHASES}

    @property
    def has_gates(self):
        return any(self.gates[p][0] or self.gates[p][1] for p in PHASES)

    @property
    def has_comp(self):
        return any(self.comp[p] for p in PHASES)

    @property
    def sense_pins(self):
        return [self.comp[p] for p in PHASES]

    @property
    def distinct_sense(self):
        s = [x for x in self.sense_pins if x]
        return len(set(s)) == 3 and len(s) == 3

    def gate_pair(self, phase):
        lo, hi = self.gates[phase]
        return (lo, hi)

    def __repr__(self):
        return "<Group {} mcu={} in={} gates={} comp={}>".format(
            self.name, self.mcu, self.input, self.gates, self.comp)


def _collect_defines(block_lines):
    """Yield (key, value, comment) for active (non-commented) #define lines."""
    for raw in block_lines:
        line = raw.strip()
        if line.startswith("//") or not line.startswith("#define"):
            continue
        body = line[len("#define"):].strip()
        comment = ""
        # split off trailing // comment
        if "//" in body:
            body, comment = body.split("//", 1)
            body = body.strip()
        parts = body.split(None, 1)
        if not parts:
            continue
        key = parts[0]
        value = parts[1].strip() if len(parts) > 1 else ""
        yield key, value, comment.strip()


def parse_targets(path=DEFAULT_TARGETS):
    """Return list[Group] for every HARDWARE_GROUP_* block in targets.h."""
    with open(path, "r", errors="replace") as fh:
        lines = fh.readlines()

    groups = []
    i = 0
    n = len(lines)
    open_re = re.compile(r"^\s*#ifdef\s+HARDWARE_GROUP_(\w+)\s*$")
    while i < n:
        m = open_re.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        # find matching #endif, tracking nested #if/#ifdef/#ifndef
        depth = 1
        j = i + 1
        block = []
        while j < n and depth > 0:
            s = lines[j].strip()
            if s.startswith("#if"):
                depth += 1
            elif s.startswith("#endif"):
                depth -= 1
                if depth == 0:
                    break
            block.append(lines[j])
            j += 1
        groups.append(_build_group(name, block))
        i = j + 1
    return groups


def _build_group(name, block):
    g = Group(name)
    # buffers for gate ports/pins keyed by (phase, role)
    pins = {}   # token name -> value
    comments = {}
    for key, value, comment in _collect_defines(block):
        pins[key] = value
        if comment:
            comments[key] = comment
        if key.startswith("MCU_"):
            g.mcu = key[4:]

    g.input = _pin_name(pins.get("INPUT_PIN_PORT"), pins.get("INPUT_PIN"))

    for p in PHASES:
        # gate low/high: either GPIO_LOW/HIGH or (bridge mode) GPIO_ENABLE/PWM
        lo = _pin_name(pins.get("PHASE_%s_GPIO_PORT_LOW" % p),
                       pins.get("PHASE_%s_GPIO_LOW" % p))
        if lo is None:
            lo = _pin_name(pins.get("PHASE_%s_GPIO_PORT_ENABLE" % p),
                           pins.get("PHASE_%s_GPIO_ENABLE" % p))
        hi = _pin_name(pins.get("PHASE_%s_GPIO_PORT_HIGH" % p),
                       pins.get("PHASE_%s_GPIO_HIGH" % p))
        if hi is None:
            hi = _pin_name(pins.get("PHASE_%s_GPIO_PORT_PWM" % p),
                           pins.get("PHASE_%s_GPIO_PWM" % p))
        g.gates[p] = [lo, hi]

        # sense pin: PHASE_x_COMP, else EXTI zero-cross pin
        comp_key = "PHASE_%s_COMP" % p
        if comp_key in pins:
            g.comp[p] = _sense_from_comp(pins[comp_key], comments.get(comp_key, ""))
        else:
            g.comp[p] = _pin_name(pins.get("PHASE_%s_EXTI_PORT" % p),
                                  pins.get("PHASE_%s_EXTI_PIN" % p))
    return g


class Target(object):
    """A concrete board target (top-level #ifdef block) in targets.h.

    A target enables one or more HARDWARE_GROUP_* via #define and sets
    FILE_NAME / FIRMWARE_NAME. `groups` is the set of HARDWARE_GROUP_* suffixes
    it turns on (e.g. {"AT_B", "AT_504"}).
    """

    def __init__(self, name):
        self.name = name
        self.file_name = None
        self.firmware_name = None
        self.groups = set()

    def __repr__(self):
        return "<Target {} file={} groups={}>".format(
            self.name, self.file_name, sorted(self.groups))


def parse_target_defs(path=DEFAULT_TARGETS):
    """Return list[Target] for every top-level board #ifdef in targets.h.

    Skips the HARDWARE_GROUP_* definition blocks themselves; only the board
    targets that *select* groups are returned.
    """
    with open(path, "r", errors="replace") as fh:
        lines = fh.readlines()

    targets = []
    i = 0
    n = len(lines)
    open_re = re.compile(r"^\s*#ifdef\s+(\w+)\s*$")
    grp_re = re.compile(r"^\s*#define\s+HARDWARE_GROUP_(\w+)")
    str_re = re.compile(r'^\s*#define\s+%s\s+"([^"]*)"')
    while i < n:
        m = open_re.match(lines[i])
        if not m or m.group(1).startswith("HARDWARE_GROUP_"):
            i += 1
            continue
        name = m.group(1)
        depth = 1
        j = i + 1
        tgt = Target(name)
        while j < n and depth > 0:
            s = lines[j].strip()
            if s.startswith("#if"):
                depth += 1
            elif s.startswith("#endif"):
                depth -= 1
                if depth == 0:
                    break
            else:
                gm = grp_re.match(lines[j])
                if gm:
                    tgt.groups.add(gm.group(1))
                fm = re.match(str_re.pattern % "FILE_NAME", lines[j])
                if fm:
                    tgt.file_name = fm.group(1)
                wm = re.match(str_re.pattern % "FIRMWARE_NAME", lines[j])
                if wm:
                    tgt.firmware_name = wm.group(1)
            j += 1
        if tgt.groups:
            targets.append(tgt)
        i = j + 1
    return targets


def used_port_pins(groups):
    """Set of every port pin (e.g. 'PB1') referenced across the given groups."""
    out = {}
    for g in groups:
        out.setdefault(g.mcu, set())
        if g.input:
            out[g.mcu].add(g.input)
        for p in PHASES:
            for x in g.gates[p]:
                if x:
                    out[g.mcu].add(x)
            if g.comp[p]:
                out[g.mcu].add(g.comp[p])
    return out


if __name__ == "__main__":
    import sys
    gs = parse_targets()
    if "--pins" in sys.argv:
        for mcu, pinset in sorted(used_port_pins(gs).items(), key=lambda kv: str(kv[0])):
            print("%-10s %s" % (mcu, " ".join(sorted(pinset,
                  key=lambda s: (s[1], int(s[2:]))))))
    else:
        for g in gs:
            kind = "base" if g.has_gates else ("comp" if g.has_comp else "?")
            print("%-8s %-6s mcu=%-8s in=%-5s gates=%s comp=%s" % (
                g.name, kind, g.mcu, g.input,
                {p: tuple(g.gates[p]) for p in PHASES},
                {p: g.comp[p] for p in PHASES}))
