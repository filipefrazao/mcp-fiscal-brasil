"""Testes do conversor TIPI (xlsx da RFB -> CSV do build_tabelas_db)."""

import importlib.util
import sqlite3
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(nome, _SCRIPTS / f"{nome}.py")
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


_LINHAS_TIPI = [
    (None, None, None, None, None),
    ("NCM ", "EX", "DESCRIÇÃO ", "ALÍQUOTA (%)", None),
    ("01.01", None, "Cavalos, asininos e muares, vivos.", "", None),
    ("0101.2", None, "- Cavalos:", "", None),
    ("0101.21.00", None, "-- Reprodutores de raça pura ", "NT", None),
    ("22.03", None, "Cervejas de malte.", "", None),
    ("2203.00.00", None, "Cervejas de malte.", 3.9000000000000004, None),
    ("2203.00.00", 1, "Chope", 3.9, None),
    ("84.71", None, "Máquinas automáticas para processamento de dados e suas unidades", "", None),
    ("8471.30", None, "- Máquinas automáticas para processamento de dados, portáteis", "", None),
    ("8471.30.1", None, "Capazes de funcionar sem fonte externa de energia", "", None),
    ("8471.30.19", None, "Outras", 15, None),
    ("8471.41", None, "- Outras máquinas", "", None),
    ("8471.41.10", None, "De peso inferior a 750 g", "9.75", None),
]


def test_converter_linhas_normaliza_codigo_aliquota_e_ex() -> None:
    mod = _carregar("tipi_xlsx_to_csv")
    registros, total_ex = mod.converter_linhas(_LINHAS_TIPI)
    por_codigo = {r["codigo"]: r for r in registros}

    assert total_ex == 1
    assert list(por_codigo) == ["01012100", "22030000", "84713019", "84714110"]
    # NT vira vazio (NULL no banco); prefixo "--" e removido; folha nao generica fica so a folha.
    assert por_codigo["01012100"]["aliquota_ipi"] == ""
    assert por_codigo["01012100"]["descricao"] == "Reprodutores de raça pura"
    # Ruido de ponto flutuante e arredondado; Ex agregado no mesmo registro.
    assert por_codigo["22030000"]["aliquota_ipi"] == "3.9"
    assert por_codigo["22030000"]["ex_tipi"] == "Ex 01: Chope (3.9%)"
    # Folha generica ("Outras") recebe a cadeia de ancestrais.
    assert por_codigo["84713019"]["descricao"] == (
        "Máquinas automáticas para processamento de dados e suas unidades > "
        "Máquinas automáticas para processamento de dados, portáteis > "
        "Capazes de funcionar sem fonte externa de energia > Outras"
    )
    assert por_codigo["84713019"]["aliquota_ipi"] == "15"
    # Ancestral de outro ramo (8471.41) nao contamina 8471.30.19 nem vice-versa.
    assert por_codigo["84714110"]["descricao"] == "De peso inferior a 750 g"
    assert por_codigo["84714110"]["aliquota_ipi"] == "9.75"


def test_csv_gerado_e_aceito_pelo_build_tabelas_db(tmp_path: Path) -> None:
    conv = _carregar("tipi_xlsx_to_csv")
    build = _carregar("build_tabelas_db")
    registros, _ = conv.converter_linhas(_LINHAS_TIPI)
    csv_path = tmp_path / "tipi.csv"
    conv.escrever_csv(registros, csv_path)

    db_path = tmp_path / "tabelas.db"
    build.build(db_path, tipi_csv=csv_path)

    conn = sqlite3.connect(db_path)
    try:
        linhas = conn.execute(
            "SELECT codigo, aliquota_ipi, ex_tipi FROM ncm ORDER BY codigo"
        ).fetchall()
    finally:
        conn.close()
    assert [linha[0] for linha in linhas] == ["01012100", "22030000", "84713019", "84714110"]
    assert linhas[0][1] is None  # NT
    assert linhas[1][1] == 3.9
    assert linhas[1][2] == "Ex 01: Chope (3.9%)"
    assert linhas[2][1] == 15.0
