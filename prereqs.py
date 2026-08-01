"""Prerequisite tree evaluation.

NUSMods returns a recursive structure for each module's prereqTree:

    "CS2030S"                              -> a single module is required
    {"and": ["CS1101S", "MA1521"]}         -> both required
    {"or":  ["CS1101S", "CS1010S"]}        -> either suffices
    {"and": ["CS1101S", {"or": [...]}]}    -> nesting allowed at any depth

This module evaluates such trees against a "completed before" set — the modules a student
has taken in semesters strictly earlier than the target semester. It also produces a
human-readable description of what's missing, for the UI.

Public API:
    prereqs_met(tree, completed_set) -> bool
    explain_unmet(tree, completed_set) -> str | None
"""
from __future__ import annotations
from typing import Iterable, Union

PrereqNode = Union[str, dict, None]


def _normalize_code(code: str) -> str:
    """NUSMods sometimes has trailing colons/grades like 'CS1101S:D'. Strip them."""
    return code.split(":")[0].strip().upper()


def prereqs_met(tree: PrereqNode, completed: Iterable[str]) -> bool:
    """True iff the prereq tree is satisfied by the `completed` set.

    An empty/None tree always evaluates True (no prereqs).
    """
    if tree is None or tree == "":
        return True
    completed_set = {c.upper() for c in completed}
    return _eval(tree, completed_set)


def _eval(node: PrereqNode, completed: set[str]) -> bool:
    if node is None:
        return True
    if isinstance(node, str):
        return _normalize_code(node) in completed
    if isinstance(node, dict):
        if "and" in node:
            children = node["and"] or []
            return all(_eval(c, completed) for c in children)
        if "or" in node:
            children = node["or"] or []
            # An empty OR is vacuously False (would require nothing AND be unsatisfiable);
            # treat as no constraint to be safe.
            return any(_eval(c, completed) for c in children) if children else True
        # NUSMods occasionally uses {"nOf": [N, [...]]} for "any N of these".
        if "nOf" in node:
            n, items = node["nOf"]
            return sum(1 for c in items if _eval(c, completed)) >= n
    # Unknown node shape: be lenient.
    return True


def explain_unmet(tree: PrereqNode, completed: Iterable[str]) -> str | None:
    """Return a short human-readable description of what's missing, or None if all met.

    Examples:
        "CS1101S"
        "CS1101S or CS1010S"
        "CS1101S and (MA1521 or MA1102R)"
    """
    if prereqs_met(tree, completed):
        return None
    completed_set = {c.upper() for c in completed}
    return _describe_unmet(tree, completed_set)


def _describe_unmet(node: PrereqNode, completed: set[str]) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return _normalize_code(node)
    if isinstance(node, dict):
        if "and" in node:
            # Only describe the children that are *not* satisfied.
            unsatisfied = [c for c in node["and"] if not _eval(c, completed)]
            # Only wrap sub-expressions when there's more than one — a sole survivor
            # doesn't need parens because there's no ambiguity at this level.
            if len(unsatisfied) == 1:
                return _describe_unmet(unsatisfied[0], completed)
            return " and ".join(_wrap(_describe_unmet(c, completed)) for c in unsatisfied)
        if "or" in node:
            # All children are unsatisfied (otherwise the OR would be met). List them.
            parts = [_wrap(_describe_unmet(c, completed)) for c in node["or"]]
            return " or ".join(parts)
        if "nOf" in node:
            n, items = node["nOf"]
            satisfied_count = sum(1 for c in items if _eval(c, completed))
            need = n - satisfied_count
            return f"{need} more of " + ", ".join(_describe_unmet(c, completed) or "?" for c in items)
    return "?"


def _wrap(s: str) -> str:
    """Parenthesize a sub-expression if it contains a connector."""
    return f"({s})" if (" and " in s or " or " in s) else s


def collect_required_codes(tree: PrereqNode) -> set[str]:
    """Return every module code that appears anywhere in the tree.

    Useful for indexing — e.g. "what modules unlock CS3243?" can be answered
    by collecting all trees that contain CS3243.
    """
    out: set[str] = set()
    _walk_collect(tree, out)
    return out


def _walk_collect(node: PrereqNode, out: set[str]) -> None:
    if node is None:
        return
    if isinstance(node, str):
        out.add(_normalize_code(node))
        return
    if isinstance(node, dict):
        for key in ("and", "or"):
            if key in node:
                for c in node[key]:
                    _walk_collect(c, out)
        if "nOf" in node:
            _, items = node["nOf"]
            for c in items:
                _walk_collect(c, out)


# ---------- Corequisite parsing ----------
#
# Corequisites in NUSMods come back as free-text strings, not a tree. Examples:
#   "CS2101"
#   "CS2101 or ES2660"
#   "CS3203 and CS2101"
#
# We parse a small subset: tokens that look like NUS module codes, optionally
# split by "and" / "or". Anything we can't recognize falls back to a free-text
# message rather than failing the check, which lets us still display the raw
# string in the UI.

_CODE_PATTERN = r"[A-Z]{2,3}\d{4}[A-Z]{0,2}"


def parse_corequisite_string(text: str | None) -> dict | None:
    """Parse a free-text corequisite string into a simple tree, or None if empty.

    The returned structure mirrors prereqTree: a string for single, {"and":[...]}
    or {"or":[...]} for compound. We don't try to be clever about nested logic;
    NUSMods coreq strings are almost always flat.

    If the string contains both "and" and "or" tokens, we conservatively split
    on "and" first, treating the result as AND of OR-groups. Edge cases produce
    {"raw": text} which the caller can show verbatim.
    """
    import re

    if not text or not text.strip():
        return None

    txt = text.strip()
    codes_only = re.fullmatch(rf"\s*{_CODE_PATTERN}\s*", txt, flags=re.IGNORECASE)
    if codes_only:
        return _normalize_code(txt)

    # Tokenize on connectors
    lowered = f" {txt.lower()} "
    has_and = " and " in lowered
    has_or = " or " in lowered

    if has_and and not has_or:
        parts = re.split(r"\s+and\s+", txt, flags=re.IGNORECASE)
        codes = [_extract_code(p) for p in parts]
        if all(codes):
            return {"and": codes}
    elif has_or and not has_and:
        parts = re.split(r"\s+or\s+", txt, flags=re.IGNORECASE)
        codes = [_extract_code(p) for p in parts]
        if all(codes):
            return {"or": codes}
    elif has_and and has_or:
        # AND of OR-groups, e.g. "CS2101 and (ES2660 or CS3215)"
        # We don't try to parse parens; just split top-level on "and".
        and_parts = re.split(r"\s+and\s+", txt, flags=re.IGNORECASE)
        sub_trees = []
        for p in and_parts:
            if " or " in p.lower():
                or_codes = [_extract_code(x) for x in re.split(r"\s+or\s+", p, flags=re.IGNORECASE)]
                if all(or_codes):
                    sub_trees.append({"or": or_codes})
                    continue
                else:
                    return {"raw": txt}
            code = _extract_code(p)
            if code:
                sub_trees.append(code)
            else:
                return {"raw": txt}
        return {"and": sub_trees} if len(sub_trees) > 1 else sub_trees[0]

    # Couldn't parse — return raw so the UI can still display it.
    return {"raw": txt}


def _extract_code(fragment: str) -> str | None:
    """Pull a single module code out of a fragment, normalizing case."""
    import re
    m = re.search(_CODE_PATTERN, fragment, flags=re.IGNORECASE)
    return m.group(0).upper() if m else None


def corequisites_met(coreq_tree: PrereqNode, completed_same_or_earlier: Iterable[str]) -> bool:
    """True iff coreq tree is satisfied by modules taken in the same semester or earlier.

    Corequisites differ from prereqs in WHEN we consider them satisfied: a coreq
    in the same semester counts, whereas a prereq needs to be strictly earlier.
    Otherwise the evaluation is the same.

    `{"raw": text}` nodes (unparseable coreq strings) always evaluate True — we
    can't enforce what we couldn't parse. The frontend should still surface the
    raw text so the user can verify manually.
    """
    if coreq_tree is None:
        return True
    if isinstance(coreq_tree, dict) and "raw" in coreq_tree:
        return True  # can't check; defer to user
    return prereqs_met(coreq_tree, completed_same_or_earlier)


# ---------- Preclusion parsing ----------
#
# Preclusions in NUSMods are also free-text. They list modules that conflict
# (you can't take CS2030S if you've already taken CS2030, etc.). Examples:
#   "CS2030, CS2030DE, IT5001"
#   "CS1101S; CS1010, CS1010X"
#
# Unlike coreqs, preclusions are essentially always a flat list — there's no
# logical structure. We just extract every NUS-style code.

def extract_preclusion_codes(text: str | None) -> set[str]:
    """Return the set of module codes mentioned in a preclusion string.

    Robust to comma, semicolon, slash, or whitespace separation. Case-insensitive
    in; uppercase out. If text is None/empty, returns an empty set.
    """
    import re
    if not text:
        return set()
    return {m.group(0).upper() for m in re.finditer(_CODE_PATTERN, text, flags=re.IGNORECASE)}
