#!/usr/bin/env python3
"""Offline pinout reference for the AM32 hardware-group finder.

Two data sets, both transcribed from manufacturer datasheets:

  * FD6288 - the Fortior 3-phase gate driver used on (virtually) every AM32 ESC.
    Both packages, FD6288T (TSSOP-20) and FD6288Q (QFN-24).

  * PINOUTS - MCU port-name -> physical leg number, per chip and per package,
    limited to the legs AM32 actually uses.

Only the legs AM32 references are listed; '-' legs (absent on a package) are simply
omitted. A chip/package that is not present here makes the tool fall back to asking
for port names directly (the firmware mapping still works, you just lose the
"touch leg N" convenience). Adding a chip = adding one verified table below.
"""

# ---------------------------------------------------------------------------
# FD6288 gate driver. Source: Fortior FD6288T&Q datasheet REV 1.3, "Lead
# Assignments". pin number -> signal name. A "channel n" half-bridge uses
# HINn (high input), LINn (low input), HOn/LOn (gate outputs) and VSn (the
# phase node that feeds the BEMF divider).
# ---------------------------------------------------------------------------
FD6288 = {
    "FD6288T (TSSOP-20)": {
        1: "HIN1", 2: "HIN2", 3: "HIN3",
        4: "LIN1", 5: "LIN2", 6: "LIN3",
        7: "VCC", 8: "COM",
        9: "LO3", 10: "LO2", 11: "LO1",
        12: "VS3", 13: "HO3", 14: "VB3",
        15: "VS2", 16: "HO2", 17: "VB2",
        18: "VS1", 19: "HO1", 20: "VB1",
    },
    "FD6288Q (QFN-24)": {
        1: "LIN1", 2: "LIN2", 3: "LIN3",
        4: "VCC", 5: "NC", 6: "COM", 7: "NC", 8: "NC",
        9: "LO3", 10: "LO2", 11: "LO1",
        12: "VS3", 13: "HO3", 14: "VB3",
        15: "VS2", 16: "HO2", 17: "VB2",
        18: "VS1", 19: "HO1", 20: "VB1",
        21: "NC", 22: "HIN1", 23: "HIN2", 24: "HIN3",
    },
}


def fd6288_pin(package, signal):
    """Leg number of an FD6288 signal name ('LIN2','VS3'...) for a package."""
    for pin, name in FD6288[package].items():
        if name == signal:
            return pin
    return None


def fd6288_channel(package, n):
    """Legs of driver channel n: dict {HIN,LIN,HO,LO,VS,VB -> leg#}."""
    return {role: fd6288_pin(package, "%s%d" % (role, n))
            for role in ("HIN", "LIN", "HO", "LO", "VS", "VB")}


# ---------------------------------------------------------------------------
# MCU pinouts.
#
# STM32F051, AT32F421 and GD32E230 share one identical pin map (Artery and
# GigaDevice designed the F421/E230 as drop-in STM32F0 parts). Verified leg
# numbers below are from the AT32F421 datasheet V2.02 "Table 5. pin definitions"
# and cross-checked against the GD32E230xx datasheet Rev 2.6 pinout figures.
# Only the four packages AM32 builds for are listed (LQFP48 for 4-in-1, and
# LQFP32 / QFN32 / QFN28 for singles); TSSOP20/LGA20 lack PB0/PA8 so cannot run
# the standard AM32 groups.
# ---------------------------------------------------------------------------
_F0 = {
    # package: { "PXn": leg }
    "LQFP48": {
        "PA0": 10, "PA1": 11, "PA2": 12, "PA3": 13, "PA4": 14, "PA5": 15,
        "PA6": 16, "PA7": 17, "PA8": 29, "PA9": 30, "PA10": 31, "PA11": 32,
        "PA12": 33, "PA13": 34, "PA14": 37, "PA15": 38,
        "PB0": 18, "PB1": 19, "PB2": 20, "PB3": 39, "PB4": 40, "PB5": 41,
        "PB6": 42, "PB7": 43, "PB13": 26, "PB14": 27, "PB15": 28,
        "PF0": 5, "PF1": 6,
    },
    "LQFP32": {
        "PA0": 6, "PA1": 7, "PA2": 8, "PA3": 9, "PA4": 10, "PA5": 11,
        "PA6": 12, "PA7": 13, "PA8": 18, "PA9": 19, "PA10": 20, "PA11": 21,
        "PA12": 22, "PA13": 23, "PA14": 24, "PA15": 25,
        "PB0": 14, "PB1": 15, "PB3": 26, "PB4": 27, "PB5": 28, "PB6": 29,
        "PB7": 30, "PF0": 2, "PF1": 3,
    },
    "QFN32": {
        "PA0": 6, "PA1": 7, "PA2": 8, "PA3": 9, "PA4": 10, "PA5": 11,
        "PA6": 12, "PA7": 13, "PA8": 18, "PA9": 19, "PA10": 20, "PA11": 21,
        "PA12": 22, "PA13": 23, "PA14": 24, "PA15": 25,
        "PB0": 14, "PB1": 15, "PB2": 16, "PB3": 26, "PB4": 27, "PB5": 28,
        "PB6": 29, "PB7": 30, "PF0": 2, "PF1": 3,
    },
    "QFN28": {
        "PA0": 6, "PA1": 7, "PA2": 8, "PA3": 9, "PA4": 10, "PA5": 11,
        "PA6": 12, "PA7": 13, "PA8": 18, "PA9": 19, "PA10": 20, "PA13": 21,
        "PA14": 22, "PA15": 23,
        "PB0": 14, "PB1": 15, "PB3": 24, "PB4": 25, "PB5": 26, "PB6": 27,
        "PB7": 28, "PF0": 2, "PF1": 3,
    },
}

# ---------------------------------------------------------------------------
# Further STM32 families, QFN packages only (the bare-leg / exposed-pad parts
# that actually appear on AM32 ESCs). Leg numbers transcribed from the official
# KiCad symbol library (gitlab.com/kicad/libraries/kicad-symbols), whose pin
# numbers come straight from the ST datasheets; the symbol used is named in each
# comment. ST keeps one pin numbering per pin-count, so these cross-check against
# _F0 (e.g. L431 QFN48 PA8=29 == _F0 LQFP48). Only AM32-referenced legs present
# on the package are listed; legs absent on a package are noted so it is obvious
# the group needing them cannot run on that package.
# ---------------------------------------------------------------------------
_G071 = {
    # G071 has no 48-pin QFN. The UFQFPN28 exists in TWO bonding variants (DS
    # Figure 9): the "GP" version STM32G071GxU (PB pins on legs 22-28) and the
    # "PD" version STM32G071GxUxN (PD0..PD3 there, plus PB15 on leg 15). ESCs use
    # the GP/PB version - that is what is listed here, transcribed from the GP
    # pinout figure. NOTE: KiCad only carries the PD (...N) symbols, so do not
    # regenerate this from KiCad. Legs 18/19 are shared remap pads: PA11/PA9 on
    # 18, PA12/PA10 on 19. PB15 does not exist on the GP version.
    "QFN28": {  # UFQFPN28 GP version, STM32G071GxU (DS Figure 9)
        "PA0": 6, "PA2": 8, "PA6": 12, "PA7": 13, "PA8": 16, "PC6": 17,
        "PA9": 18, "PA11": 18, "PA10": 19, "PA12": 19,
        "PA15": 22, "PB0": 14, "PB1": 15, "PB3": 23, "PB4": 24, "PB7": 27,
    },
    "QFN32": {  # UFQFPN32 GP version, STM32G071KxU (DS Figure 8). Here PA9/PA10
        # have dedicated legs (19/21) distinct from PA11/PA12 (22/23). No PB15.
        "PA0": 7, "PA2": 9, "PA6": 13, "PA7": 14, "PA8": 18, "PA9": 19,
        "PC6": 20, "PA10": 21, "PA11": 22, "PA12": 23,
        "PA15": 26, "PB0": 15, "PB1": 16, "PB3": 27, "PB4": 28, "PB7": 31,
    },
}
_G031 = {
    "QFN28": {  # QFN-28 4x4 (KiCad STM32G031G4Ux) - no PB13/PB14/PB15
        "PA6": 12, "PA8": 16, "PA9": 18, "PA10": 19, "PB1": 15, "PB7": 27,
        "PC14": 1,
    },
    "QFN32": {  # QFN-32 5x5 1EP (KiCad STM32G031K4Ux) - no PB13/PB14/PB15
        "PA6": 13, "PA8": 18, "PA9": 22, "PA10": 23, "PB1": 16, "PB7": 31,
        "PC14": 2,
    },
    "QFN48": {  # QFN-48 7x7 1EP (KiCad STM32G031C4Ux)
        "PA6": 17, "PA8": 28, "PA9": 33, "PA10": 34, "PB1": 20, "PB7": 46,
        "PB13": 25, "PB14": 26, "PB15": 27, "PC14": 2,
    },
}
_G431 = {
    "QFN32": {  # QFN-32 5x5 1EP (KiCad STM32G431K6Ux) - no PB1/PB13/PB14/PB15
        "PA0": 5, "PA2": 7, "PA4": 9, "PA5": 10, "PA7": 12, "PA8": 18,
        "PA9": 19, "PA10": 20, "PB0": 13, "PF0": 2,
    },
    "QFN48": {  # QFN-48 7x7 1EP (KiCad STM32G431C6Ux)
        "PA0": 8, "PA2": 10, "PA4": 12, "PA5": 13, "PA7": 15, "PA8": 30,
        "PA9": 31, "PA10": 32, "PB0": 17, "PB1": 18, "PB13": 26, "PB14": 27,
        "PB15": 28, "PF0": 5,
    },
}
_L431 = {
    "QFN32": {  # QFN-32 5x5 1EP (KiCad STM32L431KBUx)
        "PA0": 6, "PA2": 8, "PA4": 10, "PA5": 11, "PA7": 13, "PA8": 18,
        "PA9": 19, "PA10": 20, "PB0": 14, "PB1": 15, "PB7": 30,
    },
    "QFN48": {  # QFN-48 7x7 1EP (KiCad STM32L431CBUx)
        "PA0": 10, "PA2": 12, "PA4": 14, "PA5": 15, "PA7": 17, "PA8": 29,
        "PA9": 30, "PA10": 31, "PB0": 18, "PB1": 19, "PB7": 43,
    },
}
_F031 = {
    # NOTE: the F031 group in targets.h references PB13/PB14/PB15, which do not
    # exist on any STM32F031 silicon (max port-B leg is PB8) - a targets.h
    # anomaly. They are simply absent here; such a group cannot run on F031.
    "QFN28": {  # QFN-28 4x4 (KiCad STM32F031G4Ux)
        "PA2": 8, "PA5": 11, "PA6": 12, "PA8": 18, "PA9": 19, "PA10": 20,
        "PB1": 15, "PB7": 28, "PF0": 2, "PF1": 3,
    },
    "QFN32": {  # QFN-32 5x5 1EP (KiCad STM32F031K4Ux)
        "PA2": 8, "PA5": 11, "PA6": 12, "PA8": 18, "PA9": 19, "PA10": 20,
        "PB1": 15, "PB7": 30, "PF0": 2, "PF1": 3,
    },
}

# ---------------------------------------------------------------------------
# Non-ST QFN parts, transcribed by hand from the manufacturer datasheets (these
# are not in the official KiCad symbol library). Both are STM32F1-pin-alikes, so
# their 48-pin numbering matches _F0 / L431 (PA8=29, PB4=40), which cross-checks
# the transcription.
# ---------------------------------------------------------------------------
_AT415 = {
    # Artery AT32F415 datasheet V2.02, Table 5 "pin definitions": column 1 is
    # QFN32, column 2 is shared LQFP48/QFN48.
    "QFN32": {  # QFN32 4x4 (DS V2.02 Table 5, QFN32 column)
        "PA2": 8, "PA7": 13, "PA8": 18, "PA9": 19, "PA10": 20,
        "PB0": 14, "PB1": 15, "PB4": 27,
    },
    "QFN48": {  # QFN48 6x6 (DS V2.02 Table 5, LQFP48/QFN48 column)
        "PA2": 12, "PA7": 17, "PA8": 29, "PA9": 30, "PA10": 31,
        "PB0": 18, "PB1": 19, "PB4": 40,
    },
}
_CH32V203 = {
    # WCH CH32V20x/30x datasheet V2.6, Table 3-1-1: LQFP48 and QFN48 share one
    # pin-number column (verified identical to KiCad's CH32V203CxTx/LQFP48).
    # QFN20/QFN28 lack PA8 (the TIM1 high-side leg AM32 needs), so QFN48 is the
    # only QFN that can run AM32.
    "QFN48": {  # QFN48 6x6 (DS V2.6 Table 3-1-1, LQFP48/QFN48 column)
        "PA0": 10, "PA7": 17, "PA8": 29, "PA9": 30, "PA10": 31,
        "PB0": 18, "PB1": 19,
    },
}

# Chip catalog: MCU_* macro (as it appears in targets.h) -> display name,
# package table, and the datasheet provenance shown to the user.
CHIPS = {
    "F051": {
        "name": "STM32F051",
        "packages": _F0,
        "source": "STM32F0 footprint (AT32F421 DS V2.02 Table 5; GD32E230 DS Rev2.6)",
    },
    "AT421": {
        "name": "AT32F421",
        "packages": _F0,
        "source": "AT32F421 datasheet V2.02, Table 5 (pin definitions)",
    },
    "GDE23": {
        "name": "GD32E230",
        "packages": _F0,
        "source": "GD32E230xx datasheet Rev2.6, pinout figures 2-2..2-6",
    },
    "G071": {
        "name": "STM32G071",
        "packages": _G071,
        "source": "STM32G071 datasheet Figure 9 (UFQFPN28 GP version, PB pins)",
    },
    "G031": {
        "name": "STM32G031",
        "packages": _G031,
        "source": "KiCad official symbol lib (ST datasheet pin numbers), QFN only",
    },
    "G431": {
        "name": "STM32G431",
        "packages": _G431,
        "source": "KiCad official symbol lib (ST datasheet pin numbers), QFN only",
    },
    "L431": {
        "name": "STM32L431",
        "packages": _L431,
        "source": "KiCad official symbol lib (ST datasheet pin numbers), QFN only",
    },
    "F031": {
        "name": "STM32F031",
        "packages": _F031,
        "source": "KiCad official symbol lib (ST datasheet pin numbers), QFN only",
    },
    "AT415": {
        "name": "AT32F415",
        "packages": _AT415,
        "source": "AT32F415 datasheet V2.02, Table 5 (pin definitions), QFN only",
    },
    "CH32V203": {
        "name": "CH32V203",
        "packages": _CH32V203,
        "source": "WCH CH32V20x/30x datasheet V2.6, Table 3-1-1, QFN48 only",
    },
}


def chip_for_mcu(mcu):
    """Return the CHIPS entry for an MCU_* macro name, or None if unknown."""
    return CHIPS.get(mcu)


def invert_package(pkg_map):
    """{'PA2':8,...} -> {8:'PA2',...} for leg-number -> port-name lookups."""
    return {leg: port for port, leg in pkg_map.items()}


if __name__ == "__main__":
    # tiny self-consistency dump
    for pkg, table in _F0.items():
        inv = invert_package(table)
        assert len(inv) == len(table), "duplicate leg in %s" % pkg
        print("%-7s %2d pins  PA2=leg%s  PB1=leg%s  PA8=leg%s"
              % (pkg, len(table), table.get("PA2"), table.get("PB1"),
                 table.get("PA8")))
    for ch in ("FD6288T (TSSOP-20)", "FD6288Q (QFN-24)"):
        print(ch, "channel2:", fd6288_channel(ch, 2))
