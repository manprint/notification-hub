"""Header di esecuzione fuori dai limiti delle colonne: ignorati, mai 500 (spec 6.2, I-7)."""

import pytest

from app.services.severity import (
    InvalidPatternError,
    compile_pattern,
    parse_duration_ms,
    parse_exit_code,
)


@pytest.mark.unit
def test_exit_code_fuori_dall_intero_a_32_bit_viene_ignorato():
    assert parse_exit_code("2147483648") is None
    assert parse_exit_code("-2147483649") is None


@pytest.mark.unit
def test_exit_code_ai_limiti_dell_intero_a_32_bit_e_accettato():
    assert parse_exit_code("2147483647") == 2147483647
    assert parse_exit_code("-2147483648") == -2147483648
    assert parse_exit_code("0") == 0


@pytest.mark.unit
def test_duration_ms_oltre_il_bigint_viene_ignorata():
    assert parse_duration_ms("9223372036854775808") is None


@pytest.mark.unit
def test_duration_ms_al_limite_del_bigint_e_accettata():
    assert parse_duration_ms("9223372036854775807") == 9223372036854775807


@pytest.mark.unit
def test_pattern_con_byte_nul_non_e_compilabile():
    """Il NUL non entra in una colonna text di Postgres: il pattern va rifiutato
    come non compilabile (422 in creazione) invece di fallire in INSERT."""
    with pytest.raises(InvalidPatternError):
        compile_pattern("a\x00b", case_insensitive=True)
