"""
knowledge_graph.py
Simple knowledge graph for disambiguating university names and group aliases
before passing questions to the SQL generator.

Usage:
    from knowledge_graph import resolve

    resolved, notes = resolve("How do Oxbridge universities compare?")
    # resolved → "How do Oxford, Cambridge universities compare?"
    # notes    → ["'Oxbridge' → Oxford, Cambridge"]
"""

from __future__ import annotations
import re

# ---------------------------------------------------------------------------
# 1. CANONICAL ALIASES
#    User says X → stored in DB as Y (one-to-one)
# ---------------------------------------------------------------------------
ALIASES: dict[str, str] = {
    # Full official names → short DB name
    "university of cambridge":          "Cambridge",
    "university of oxford":             "Oxford",
    "university of london":             "UCL",
    "university college london":        "UCL",
    "imperial college london":          "Imperial College",
    "imperial college":                 "Imperial College",
    "london school of economics":       "London School of Economics",
    "london school of economics and political science": "London School of Economics",
    "king's college london":            "King's College London",
    "kings college london":             "King's College London",
    "queen mary university of london":  "Queen Mary",
    "queen mary, university of london": "Queen Mary",
    "school of oriental and african studies": "SOAS",
    "university of st andrews":         "St Andrews",
    "university of edinburgh":          "Edinburgh",
    "university of glasgow":            "Glasgow",
    "university of aberdeen":           "Aberdeen",
    "university of dundee":             "Dundee",
    "university of strathclyde":        "Strathclyde",
    "heriot watt":                      "Heriot-Watt",
    "university of bristol":            "Bristol",
    "university of bath":               "Bath",
    "university of exeter":             "Exeter",
    "university of warwick":            "Warwick",
    "university of york":               "York",
    "university of durham":             "Durham",
    "university of leeds":              "Leeds",
    "university of sheffield":          "Sheffield",
    "university of manchester":         "Manchester",
    "university of birmingham":         "Birmingham",
    "university of nottingham":         "Nottingham",
    "university of liverpool":          "Liverpool",
    "university of newcastle":          "Newcastle",
    "university of southampton":        "Southampton",
    "university of surrey":             "Surrey",
    "university of sussex":             "Sussex",
    "university of kent":               "Kent",
    "university of leicester":          "Leicester",
    "university of hull":               "Hull",
    "university of reading":            "Reading",
    "university of east anglia":        "UEA",
    "east anglia":                      "UEA",
    "university of ulster":             "Ulster",
    "queen's university belfast":       "Queen's, Belfast",
    "queens university belfast":        "Queen's, Belfast",
    "university of cardiff":            "Cardiff",
    "cardiff university":               "Cardiff",
    "university of swansea":            "Swansea",
    "swansea university":               "Swansea",
    "university of aberystwyth":        "Aberystwyth",
    "aberystwyth university":           "Aberystwyth",
    # Common abbreviations / nicknames
    "lse":                              "London School of Economics",
    "ucl":                              "UCL",
    "kcl":                              "King's College London",
    "qmul":                             "Queen Mary",
    "uwe":                              "UWE Bristol",
    "ljmu":                             "Liverpool John Moores",
    "mmu":                              "Manchester Met",
    "lmu":                              "Leeds Met",
    "lbu":                              "Leeds Met",
    "brookes":                          "Oxford Brookes",
    "goldsmiths":                       "Goldsmiths",
}

# ---------------------------------------------------------------------------
# 2. GROUP EXPANSIONS
#    User says X → list of DB institution names (one-to-many)
# ---------------------------------------------------------------------------
GROUPS: dict[str, list[str]] = {
    "oxbridge": [
        "Oxford",
        "Cambridge",
    ],
}


# ---------------------------------------------------------------------------
# 3. RESOLUTION LOGIC
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Lowercase and strip punctuation for matching."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def resolve(question: str) -> tuple[str, list[str]]:
    """
    Scan the question for known aliases and group names.
    Returns:
        resolved_question : str   — question with aliases replaced by DB names
        notes             : list  — human-readable disambiguation log
    """
    notes: list[str] = []
    replaced_spans: list[tuple[int, int]] = []

    def already_replaced(m: re.Match) -> bool:
        for start, end in replaced_spans:
            if m.start() < end and m.end() > start:
                return True
        return False

    resolved = question

    # 1. Group expansions (one → many) — longer phrases first
    for group_key, members in sorted(GROUPS.items(), key=lambda x: -len(x[0])):
        pattern = re.compile(re.escape(group_key), re.IGNORECASE)
        match = pattern.search(resolved)
        if match and not already_replaced(match):
            members_str = ", ".join(f"'{m}'" for m in members)
            in_clause = f"({members_str})"
            resolved = resolved[:match.start()] + in_clause + resolved[match.end():]
            replaced_spans.append((match.start(), match.start() + len(in_clause)))
            notes.append(f"'{group_key}' → {', '.join(members)}")

    # 2. Alias substitutions (one → one) — longer aliases first, skip replaced spans
    for alias, canonical in sorted(ALIASES.items(), key=lambda x: -len(x[0])):
        pattern = re.compile(re.escape(alias), re.IGNORECASE)
        match = pattern.search(resolved)
        if match and not already_replaced(match):
            replacement = f"'{canonical}'"
            resolved = resolved[:match.start()] + replacement + resolved[match.end():]
            replaced_spans.append((match.start(), match.start() + len(replacement)))
            notes.append(f"'{alias}' → {canonical}")

    if not notes:
        notes.append("No aliases detected")

    return resolved, notes

