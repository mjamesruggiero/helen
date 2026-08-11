"""Tests for helen.post
"""
import pytest

from helen.load import load_raw

def test_load_raw_filters_posted(tmp_path):
    p = tmp_path / "mini.csv"
    p.write_text(
        '"DATE","DESCRIPTION","AMOUNT","CHECK #","STATUS"\n'
        '"08/07/2026","PURCHASE ... CARD 9299","-7.99","","Posted"\n'
        '"08/07/2026","PENDING THING","-1.00","","Pending"\n'
    )
    df = load_raw(p)
    assert len(df) == 1
    assert df.iloc[0]["STATUS"] == "Posted"
