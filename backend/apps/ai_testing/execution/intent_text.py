"""Derive an objectively checkable display value from an assertion target.

Global plans often describe an ``element_state exists`` target only by intent, for example
"monitoring view status control showing To Do". The trailing phrase names the text the control
must display, which lets the runtime bind the assertion deterministically when exactly one
discovered element shows that text. Selectors anchored on an attribute (id, title, aria-label,
data-testid) are preferred over structural ``nth-of-type`` chains because repeated list rows
usually share their label text while the control the author meant carries the attribute.
"""

from __future__ import annotations

import re
from typing import Any

_QUOTED_VALUE = re.compile(r'["“「『](?P<value>[^"”」』]{1,80})["”」』]')
_TRAILING_VALUE = re.compile(
    r'(?:\b(?:showing|shows|displaying|displays|reading|reads|labell?ed|titled|named|set to|equal to|equals|'
    r'that says|saying|with (?:the )?(?:text|label|value|caption))\s+)'
    r'(?P<value>[^,;:.。]{1,80}?)\s*[.。]?\s*$',
    re.IGNORECASE,
)
_STRUCTURAL_SELECTOR = re.compile(r':nth-(?:of-type|child)\(| > |\s>\s|^text=')


def display_value_from_target(target: dict[str, Any] | None) -> str:
    """Return the text an intent-only target must display, or '' when the intent names none."""
    if not isinstance(target, dict):
        return ''
    explicit = str(target.get('text') or '').strip()
    if explicit:
        return explicit
    intent = str(target.get('intent') or '').strip()
    if not intent:
        return ''
    quoted = _QUOTED_VALUE.search(intent)
    if quoted:
        return quoted.group('value').strip()
    trailing = _TRAILING_VALUE.search(intent)
    if trailing:
        value = trailing.group('value').strip().strip('"\'“”')
        # Reject phrases that only name another element rather than a literal value.
        if value and len(value.split()) <= 6 and not value.lower().startswith(('a ', 'an ', 'the ')):
            return value
    return ''


def is_anchored_selector(selector: str) -> bool:
    """True for attribute/id anchored selectors, False for structural nth-of-type chains."""
    candidate = str(selector or '').strip()
    return bool(candidate) and not _STRUCTURAL_SELECTOR.search(candidate)


_CHOICE_ROLES = frozenset({'option', 'menuitem', 'menuitemcheckbox', 'menuitemradio'})


def is_choice_element(element: dict[str, Any]) -> bool:
    """True for an option inside an open menu or listbox, which never displays a committed value."""
    role = str(element.get('role') or '').strip().casefold()
    tag = str(element.get('tag') or '').strip().casefold()
    try:
        group_size = int(element.get('group_size') or 0)
    except (TypeError, ValueError):
        group_size = 0
    return role in _CHOICE_ROLES or tag == 'option' or (bool(element.get('top_layer')) and group_size > 1)


def exact_text_locator(
    value: str,
    elements: list[dict[str, Any]],
    *,
    allow_containing: bool = False,
    skip_choices: bool = False,
    case_sensitive: bool = False,
) -> str:
    """Return the single locator whose visible text equals ``value``, preferring anchored selectors.

    With ``allow_containing`` elements whose text merely contains the value are considered when nothing
    matches exactly; with ``skip_choices`` menu options are ignored so a still-open list cannot be bound
    as the control that displays the chosen value; ``case_sensitive`` keeps "close" (an icon button's
    label) from matching a committed value "Close". Returns '' when nothing matches or the match stays
    ambiguous after the anchored tie-break.
    """
    expected = ' '.join(str(value or '').split())
    if not case_sensitive:
        expected = expected.casefold()
    if not expected:
        return ''
    exact: dict[str, None] = {}
    containing: dict[str, None] = {}
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        if skip_choices and is_choice_element(element):
            continue
        selector = str(element.get('selector') or '').strip()
        visible_text = ' '.join(str(element.get('name') or element.get('text') or '').split())
        if not case_sensitive:
            visible_text = visible_text.casefold()
        if not selector or not visible_text:
            continue
        if visible_text == expected:
            exact.setdefault(selector, None)
        elif allow_containing and expected in visible_text and len(visible_text) <= len(expected) + 40:
            containing.setdefault(selector, None)
    matches = exact or containing
    if not matches:
        return ''
    anchored = [selector for selector in matches if is_anchored_selector(selector)]
    chosen = anchored or innermost_selectors(list(matches))
    return chosen[0] if len(chosen) == 1 else ''


def innermost_selectors(selectors: list[str]) -> list[str]:
    """Drop structural selectors that are ancestors of another candidate (a wrapper repeating its child's text)."""
    return [
        selector
        for selector in selectors
        if not any(other != selector and other.startswith(f'{selector} > ') for other in selectors)
    ]


def selectors_are_nested(left: str, right: str) -> bool:
    """True when one structural selector is an ancestor of the other."""
    left, right = str(left or '').strip(), str(right or '').strip()
    return bool(left and right) and (left == right or left.startswith(f'{right} > ') or right.startswith(f'{left} > '))


_GENERIC_POPUP_WORDS = frozenset({
    'dialog', 'dialogue', 'modal', 'popup', 'pop', 'window', 'confirmation', 'confirm', 'confirming', 'prompt',
    'panel', 'overlay', 'box', 'layer', 'drawer', 'sheet', 'toast', 'notification', 'message', 'the', 'and',
    'for', 'with', 'that', 'this', 'appears', 'appear', 'shown', 'show', 'shows', 'showing', 'open', 'opened',
    'opens', 'opening', 'visible', 'displayed', 'display', 'displaying', 'screen', 'page', 'view', 'after',
    'from', 'new', 'current', 'its', 'should', 'must', 'will', 'has', 'have', 'been', 'being', 'into', 'onto',
})


def popup_intent_mismatch(intent: str, dialog_text: str) -> str:
    """Explain why the visible dialog cannot be the one the intent names, or '' when it can.

    "download confirmation dialog" names a download; a dialog whose text never mentions downloading is a
    different dialog (for example the neighbouring toolbar button's). Only Latin word stems are compared, and
    an intent without a distinctive word, or a dialog without readable text, is never judged a mismatch.
    """
    tokens = [
        token
        for token in re.findall(r'[a-z][a-z0-9-]{2,}', str(intent or '').casefold())
        if token not in _GENERIC_POPUP_WORDS
    ]
    preview = ' '.join(str(dialog_text or '').split())
    text = preview.casefold()
    if not tokens or len(text) < 3:
        return ''
    for token in tokens:
        stem = token[:5] if len(token) >= 6 else token
        if stem in text:
            return ''
    return (
        f'The open dialog does not match "{intent}"; its visible text begins "{preview[:80]}". '
        'Close it and choose a different control.'
    )


def expects_true(value: Any) -> bool:
    """Plans serialise the expected value of an existence assertion as True, "true", "True", "1" or "yes"."""
    if value is True:
        return True
    return str(value or '').strip().casefold() in {'true', '1', 'yes'}


# Words that name the kind of control rather than which control. An intent says "site name search input"
# while the control calls itself "Search site name..." — the subject words agree and only the type word
# differs, yet requiring every word to match refused the binding and left the step unbindable. These are
# dropped before matching so the subject has to agree and the type word does not.
CONTROL_TYPE_WORDS = frozenset({
    'input', 'box', 'field', 'textbox', 'searchbox', 'combobox', 'textarea',
    'button', 'btn', 'icon', 'control', 'controls', 'toggle', 'switch', 'checkbox', 'radio',
    'label', 'header', 'heading', 'title', 'tab', 'link', 'bar', 'widget', 'component',
    'container', 'wrapper', 'block', 'region', 'pane', 'column', 'cell', 'group',
})


def subject_tokens(tokens: set[str]) -> set[str]:
    """The words that say *which* thing, with layout and control-type words removed.

    Returns the original set when nothing distinctive is left: an intent made only of type words carries no
    subject, and matching on an empty set would match every control on the page.
    """
    subject = {token for token in tokens if token not in CONTROL_TYPE_WORDS and token not in _GENERIC_COLLECTION_WORDS}
    return subject or set(tokens)


_GENERIC_COLLECTION_WORDS = frozenset({
    'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'onto', 'after', 'before', 'under', 'over',
    'all', 'any', 'each', 'its', 'their', 'are', 'was', 'were', 'been', 'being', 'has', 'have', 'not',
    'list', 'listed', 'lists', 'item', 'items', 'entry', 'entries', 'row', 'rows', 'result', 'results',
    'record', 'records', 'card', 'cards', 'element', 'elements', 'shown', 'showing', 'displayed', 'visible',
    'matching', 'selected', 'target', 'current', 'page', 'area', 'view', 'section', 'panel', 'table', 'grid',
    'loaded', 'loading', 'available', 'opened', 'open', 'new', 'first', 'last', 'count', 'number',
})

_CONTINUABLE_COLLECTION_OPERATORS = frozenset({'greater_than', 'greater_than_or_equal', 'exists'})


def significant_tokens(text: str) -> set[str]:
    """Lower-cased Latin words of an intent that name its subject; list/layout words carry no meaning here."""
    return {
        token
        for token in re.findall(r'[a-z][a-z0-9-]{2,}', str(text or '').casefold())
        if token not in _GENERIC_COLLECTION_WORDS
    }


def shared_intent_tokens(left: str, right: str) -> int:
    """Count the subject words two intents share; words agreeing on their first five letters count as one."""

    def stem(token: str) -> str:
        return token[:5] if len(token) >= 6 else token

    return len({stem(token) for token in significant_tokens(left)} & {stem(token) for token in significant_tokens(right)})


def continuing_collection_locator(
    intent: str,
    verified_predecessors: list[dict[str, Any]] | None,
    present_locators: set[str] | None = None,
) -> str:
    """Locator of the verified predecessor collection that ``intent`` continues, or '' when none does.

    A verify-only step ("wait for the site camera list to finish loading") asserts on the same repeated items a
    predecessor already proved. Among predecessor collection assertions that expect a non-empty group and whose
    bound locator is still present on the page, the one sharing the most subject words with ``intent`` wins;
    later predecessors win ties because they describe the most recent page state. Collections sharing no subject
    word are unrelated and nothing is inherited.
    """
    best_locator, best_score = '', 0
    for predecessor in verified_predecessors or []:
        if not isinstance(predecessor, dict):
            continue
        for assertion in predecessor.get('assertions') or []:
            if not isinstance(assertion, dict) or assertion.get('assert_kind') != 'collection':
                continue
            if assertion.get('operator') not in _CONTINUABLE_COLLECTION_OPERATORS:
                continue
            target = assertion.get('target') if isinstance(assertion.get('target'), dict) else {}
            locator = str(target.get('locator') or '').strip()
            if not locator:
                continue
            score = shared_intent_tokens(intent, str(target.get('intent') or ''))
            if score >= 1 and score >= best_score:
                best_locator, best_score = locator, score
    # The best-matching collection is the one the intent means; when it has left the page, a weaker match
    # would be a different list, so nothing is inherited rather than the wrong group.
    if present_locators is not None and best_locator not in present_locators:
        return ''
    return best_locator
