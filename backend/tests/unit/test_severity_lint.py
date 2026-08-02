"""D8: app/services/severity.py e l'unico modulo autorizzato a importare `re2`,
e nessun modulo che valuta pattern utente puo importare il modulo `re` della
standard library (invariante I-3: niente ReDoS strutturale)."""

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


def _imports_stdlib_re(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "re":
                    return True
        if isinstance(node, ast.ImportFrom) and node.module == "re":
            return True
    return False


@pytest.mark.unit
def test_nessun_modulo_importa_re_stdlib():
    offenders = [str(p) for p in APP_ROOT.rglob("*.py") if _imports_stdlib_re(p)]
    assert offenders == [], f"Moduli che importano 're' (stdlib): {offenders}"


@pytest.mark.unit
def test_solo_severity_py_importa_re2():
    offenders = [
        str(p) for p in APP_ROOT.rglob("*.py") if "re2" in p.read_text() and p.name != "severity.py"
    ]
    assert offenders == [], f"Moduli diversi da severity.py che citano re2: {offenders}"
