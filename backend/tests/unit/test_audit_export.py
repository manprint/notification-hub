"""Export CSV dell'audit: le celle che Excel valuta come formule vanno neutralizzate."""

import pytest

from app.api.v1.audit import _csv_cell


@pytest.mark.unit
@pytest.mark.parametrize(
    "valore", ["=1+1", "+39 02", "-cmd|' /C calc'!A1", "@SUM(A1)", "\tx", "\rx"]
)
def test_cella_con_prefisso_da_formula_riceve_un_apice(valore: str) -> None:
    assert _csv_cell(valore) == f"'{valore}"


@pytest.mark.unit
def test_cella_innocua_e_altri_tipi_restano_invariati() -> None:
    assert _csv_cell("Backup notturno") == "Backup notturno"
    assert _csv_cell("") == ""
    assert _csv_cell(None) is None
    assert _csv_cell(3) == 3
