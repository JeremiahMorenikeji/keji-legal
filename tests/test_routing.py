import pytest
from api.agents.routing_agent import classify


@pytest.mark.parametrize("text,expected", [
    ("GDPR data breach 72-hour notification", "EU"),
    ("Delaware corporation formation requirements", "US"),
    ("Canada Business Corporations Act directors", "CA"),
    ("UK Employment Rights Act unfair dismissal", "UK"),
    ("Does U.S. federal law require this?", "US"),
])
def test_unambiguous_queries(text, expected):
    r = classify(text)
    assert r["suggestion"] == expected and r["method"] == "regex"


@pytest.mark.parametrize("text", [
    "discuss the business impact of regulation",
    "focus on the usual suspects",
    "Eurovision contest rules",       # must not trigger EU via substring
])
def test_substring_false_positives_do_not_match_regex(text):
    assert classify(text)["method"] != "regex"


def test_tie_is_ambiguous():
    r = classify("Compare Canada and England")
    assert r["suggestion"] == "AMBIGUOUS" and r["tie"] is True


def test_acronyms_are_case_sensitive():
    assert classify("the sec of the table")["method"] != "regex"   # 'sec' ≠ SEC
