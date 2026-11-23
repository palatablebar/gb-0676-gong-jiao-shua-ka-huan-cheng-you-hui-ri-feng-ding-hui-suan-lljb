from app.modules.m8_settlement.rules import evaluate
from app.errors import DomainError
import pytest
def test_real_sample_archive_ready(result): assert result["stages"][7]["metrics"]["ready"] is True
def test_real_sample_archive_source_count(result): assert result["stages"][7]["metrics"]["source_lines"]==result["stages"][6]["metrics"]["accepted_inputs"]
def test_real_sample_seal_stable(result):
    rows=result["stages"][6]["rows"];assert evaluate(rows,{})["metrics"]["sha256"]==evaluate(rows,{})["metrics"]["sha256"]
def test_unbalanced_blocked():
    with pytest.raises(DomainError) as e:evaluate([],{"reconcile":{"metrics":{"balanced":False}}})
    assert e.value.code=="UNBALANCED"
def test_duplicate_archive_key():
    with pytest.raises(DomainError):evaluate([{"event_id":"1"},{"event_id":"1"}],{})
def test_real_sample_manifest_has_hash(result): assert len(result["manifest"]["input_sha256"])==64
def test_real_sample_export_rows_match(result): assert result["stages"][7]["rows"]==result["stages"][6]["rows"]
def test_duplicate_comp_ledger_blocked():
    ledger=[{"comp_key":"01|2026-11-23"},{"comp_key":"01|2026-11-23"}]
    with pytest.raises(DomainError) as e:evaluate([],{"emergency":{"metrics":{"balanced":True},"compensation_ledger":ledger}})
    assert e.value.code=="LEDGER_DUPLICATE"
def test_typhoon_ledger_unique(typhoon_result):
    stage=typhoon_result["stages"][7]
    keys=[x["comp_key"] for x in stage["compensation_ledger"]]
    assert len(keys)==len(set(keys)) and stage["metrics"]["ready"] is True
