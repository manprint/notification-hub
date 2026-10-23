"""Il log della violazione di vincolo non deve riportare il valore duplicato."""

import pytest
from asyncpg.exceptions import UniqueViolationError
from sqlalchemy.exc import IntegrityError

from app import main as main_module


class _LoggerRegistrante:
    def __init__(self) -> None:
        self.eventi: list[tuple[str, dict]] = []

    def warning(self, event: str, **kwargs: object) -> None:
        self.eventi.append((event, kwargs))

    def exception(self, event: str, **kwargs: object) -> None:
        self.eventi.append((event, kwargs))


@pytest.mark.unit
async def test_violazione_di_unicita_non_scrive_l_email_nel_log(monkeypatch):
    logger = _LoggerRegistrante()
    monkeypatch.setattr(main_module, "get_logger", lambda _name: logger)
    app = main_module.create_app()

    # Forma che asyncpg dà a Postgres: il DETAIL riporta il valore duplicato.
    driver = UniqueViolationError('duplicate key value violates unique constraint "uq_users_email"')
    driver.detail = "Key (email)=(duplicata@example.test) already exists."
    driver.constraint_name = "uq_users_email"
    driver.table_name = "users"
    # Il wrapper di SQLAlchemy incarta il messaggio completo, DETAIL compreso: la
    # vecchia riga logava str(exc.orig), quindi l'email arrivava nel log.
    orig = RuntimeError(f"{driver}\nDETAIL:  {driver.detail}")
    orig.__cause__ = driver
    exc = IntegrityError("INSERT INTO users", {}, orig)

    handler = app.exception_handlers[IntegrityError]
    await handler(None, exc)

    assert logger.eventi, "il handler deve loggare la violazione"
    assert "duplicata@example.test" not in repr(logger.eventi)
    assert any(kw.get("constraint") == "uq_users_email" for _, kw in logger.eventi)
