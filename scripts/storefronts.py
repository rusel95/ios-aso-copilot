#!/usr/bin/env python3
"""Single source of truth for Apple App Store storefront codes.

All 155 App Store storefronts, ISO-2 country code -> `X-Apple-Store-Front` header value, sourced
from Apple's own affiliate documentation storefront ID table (gist.github.com/hmml/8942940,
cross-checked against the subset already verified live in this skill on 2026-08-19). Storefront IDs
are assigned once when a country's store opens and Apple has never reassigned one.

Before this file existed, `rank_audit.py` and `harvest_keywords.py` each carried their own
hand-copied storefront dict — 24 markets in one, 4 in the other — and every fix to one silently
missed the other. `ro`, `no` and `se` were absent from `rank_audit.py`'s dict entirely despite
being real, working App Store storefronts; `harvest_keywords.py` supported only us/gb/de/ua. That
divergence is why `--expand-from-hints` returned 0 queries for `ro`/`il` — not because Apple doesn't
serve those markets, but because neither dict had ever been asked to.

Both scripts import STOREFRONTS from here. A market missing from this file is a market Apple
genuinely does not run an App Store storefront for, not an oversight in either script.
"""
from __future__ import annotations

# ISO-2 -> Apple's `X-Apple-Store-Front` header value for the MZSearchHints autocomplete endpoint.
STOREFRONTS: dict[str, str] = {
    "ae": "143481-1,29", "ag": "143540-1,29", "ai": "143538-1,29", "al": "143575-1,29",
    "am": "143524-1,29", "ao": "143564-1,29", "ar": "143505-1,29", "at": "143445-1,29",
    "au": "143460-1,29", "az": "143568-1,29", "bb": "143541-1,29", "be": "143446-1,29",
    "bf": "143578-1,29", "bg": "143526-1,29", "bh": "143559-1,29", "bj": "143576-1,29",
    "bm": "143542-1,29", "bn": "143560-1,29", "bo": "143556-1,29", "br": "143503-1,29",
    "bs": "143539-1,29", "bt": "143577-1,29", "bw": "143525-1,29", "by": "143565-1,29",
    "bz": "143555-1,29", "ca": "143455-1,29", "cg": "143582-1,29", "ch": "143459-1,29",
    "cl": "143483-1,29", "cn": "143465-1,29", "co": "143501-1,29", "cr": "143495-1,29",
    "cv": "143580-1,29", "cy": "143557-1,29", "cz": "143489-1,29", "de": "143443-1,29",
    "dk": "143458-1,29", "dm": "143545-1,29", "do": "143508-1,29", "dz": "143563-1,29",
    "ec": "143509-1,29", "ee": "143518-1,29", "eg": "143516-1,29", "es": "143454-1,29",
    "fi": "143447-1,29", "fj": "143583-1,29", "fm": "143591-1,29", "fr": "143442-1,29",
    "gb": "143444-1,29", "gd": "143546-1,29", "gh": "143573-1,29", "gm": "143584-1,29",
    "gr": "143448-1,29", "gt": "143504-1,29", "gw": "143585-1,29", "gy": "143553-1,29",
    "hk": "143463-1,29", "hn": "143510-1,29", "hr": "143494-1,29", "hu": "143482-1,29",
    "id": "143476-1,29", "ie": "143449-1,29", "il": "143491-1,29", "in": "143467-1,29",
    "is": "143558-1,29", "it": "143450-1,29", "jm": "143511-1,29", "jo": "143528-1,29",
    "jp": "143462-1,29", "ke": "143529-1,29", "kg": "143586-1,29", "kh": "143579-1,29",
    "kn": "143548-1,29", "kr": "143466-1,29", "kw": "143493-1,29", "ky": "143544-1,29",
    "kz": "143517-1,29", "la": "143587-1,29", "lb": "143497-1,29", "lc": "143549-1,29",
    "lk": "143486-1,29", "lr": "143588-1,29", "lt": "143520-1,29", "lu": "143451-1,29",
    "lv": "143519-1,29", "md": "143523-1,29", "mg": "143531-1,29", "mk": "143530-1,29",
    "ml": "143532-1,29", "mn": "143592-1,29", "mo": "143515-1,29", "mr": "143590-1,29",
    "ms": "143547-1,29", "mt": "143521-1,29", "mu": "143533-1,29", "mw": "143589-1,29",
    "mx": "143468-1,29", "my": "143473-1,29", "mz": "143593-1,29", "na": "143594-1,29",
    "ne": "143534-1,29", "ng": "143561-1,29", "ni": "143512-1,29", "nl": "143452-1,29",
    "no": "143457-1,29", "np": "143484-1,29", "nz": "143461-1,29", "om": "143562-1,29",
    "pa": "143485-1,29", "pe": "143507-1,29", "pg": "143597-1,29", "ph": "143474-1,29",
    "pk": "143477-1,29", "pl": "143478-1,29", "pt": "143453-1,29", "pw": "143595-1,29",
    "py": "143513-1,29", "qa": "143498-1,29", "ro": "143487-1,29", "ru": "143469-1,29",
    "sa": "143479-1,29", "sb": "143601-1,29", "sc": "143599-1,29", "se": "143456-1,29",
    "sg": "143464-1,29", "si": "143499-1,29", "sk": "143496-1,29", "sl": "143600-1,29",
    "sn": "143535-1,29", "sr": "143554-1,29", "st": "143598-1,29", "sv": "143506-1,29",
    "sz": "143602-1,29", "tc": "143552-1,29", "td": "143581-1,29", "th": "143475-1,29",
    "tj": "143603-1,29", "tm": "143604-1,29", "tn": "143536-1,29", "tr": "143480-1,29",
    "tt": "143551-1,29", "tw": "143470-1,29", "tz": "143572-1,29", "ua": "143492-1,29",
    "ug": "143537-1,29", "us": "143441-1,29", "uy": "143514-1,29", "uz": "143566-1,29",
    "vc": "143550-1,29", "ve": "143502-1,29", "vg": "143543-1,29", "vn": "143471-1,29",
    "ye": "143571-1,29", "za": "143472-1,29", "zw": "143605-1,29",
}

ALL_STOREFRONT_CODES: list[str] = sorted(STOREFRONTS)


def self_check() -> None:
    assert len(STOREFRONTS) == 155, f"expected 155 storefronts, got {len(STOREFRONTS)}"
    for code, value in STOREFRONTS.items():
        assert len(code) == 2 and code == code.lower(), f"bad code {code!r}"
        assert value.endswith("-1,29") and value[:-5].isdigit(), f"bad header value for {code!r}: {value!r}"
    # Markets this incident specifically surfaced as missing before this file existed.
    for code in ("ro", "no", "se", "il"):
        assert code in STOREFRONTS, f"{code!r} must be present — this is the exact gap that caused it"
    print(f"OK — {len(STOREFRONTS)} storefronts, all header values well-formed")


if __name__ == "__main__":
    self_check()
