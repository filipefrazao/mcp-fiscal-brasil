"""Comparativo entre regimes tributarios brasileiros.

Calculo simplificado, baseado em premissas publicas e tabelas vigentes em 2025.
Não substitui parecer de contador. Util para estimativa rápida e direcionamento.

Simples Nacional: aliquota efetiva conforme LC 123/2006, art. 18, par. 1o-A
(Anexos I, II, III e V na redacao da LC 155/2016), ou seja, aplicando a parcela
a deduzir de cada faixa sobre a receita bruta acumulada (RBT12). Lucro
Presumido: presuncoes de 8%/32% (IRPJ) e 12%/32% (CSLL), com adicional de IRPJ
de 10% sobre o lucro presumido que excede R$ 240 mil/ano.
"""

from __future__ import annotations

from typing import Literal

from .schemas import TaxRegimeComparison, TaxRegimeOption

_LIMITE_MEI = 81_000.0
_LIMITE_SIMPLES = 4_800_000.0
_LIMITE_LUCRO_PRESUMIDO = 78_000_000.0
_LIMITE_ADICIONAL_IRPJ_ANUAL = 240_000.0  # R$ 20 mil/mes (R$ 60 mil/trimestre)

# Anexos do Simples Nacional (LC 123/2006, redacao da LC 155/2016):
# (limite superior da faixa de RBT12, aliquota nominal %, parcela a deduzir R$).
# Anexo IV (construcao, vigilancia, limpeza, advocacia) nao e coberto pelos
# setores aceitos por compare_tax_regimes.
_FAIXAS_SIMPLES: dict[str, list[tuple[float, float, float]]] = {
    "I": [  # Comercio
        (180_000, 4.0, 0.0),
        (360_000, 7.3, 5_940.0),
        (720_000, 9.5, 13_860.0),
        (1_800_000, 10.7, 22_500.0),
        (3_600_000, 14.3, 87_300.0),
        (4_800_000, 19.0, 378_000.0),
    ],
    "II": [  # Industria
        (180_000, 4.5, 0.0),
        (360_000, 7.8, 5_940.0),
        (720_000, 10.0, 13_860.0),
        (1_800_000, 11.2, 22_500.0),
        (3_600_000, 14.7, 85_500.0),
        (4_800_000, 30.0, 720_000.0),
    ],
    "III": [  # Servicos com Fator R >= 28%
        (180_000, 6.0, 0.0),
        (360_000, 11.2, 9_360.0),
        (720_000, 13.5, 17_640.0),
        (1_800_000, 16.0, 35_640.0),
        (3_600_000, 21.0, 125_640.0),
        (4_800_000, 33.0, 648_000.0),
    ],
    "V": [  # Servicos com Fator R < 28%
        (180_000, 15.5, 0.0),
        (360_000, 18.0, 4_500.0),
        (720_000, 19.5, 9_900.0),
        (1_800_000, 20.5, 17_100.0),
        (3_600_000, 23.0, 62_100.0),
        (4_800_000, 30.5, 540_000.0),
    ],
}


def _imposto_simples(rbt12: float, anexo: str) -> float:
    """Imposto anual do Simples = RBT12 x aliquota nominal - parcela a deduzir.

    Equivale a aplicar a aliquota efetiva da LC 123/2006, art. 18, par. 1o-A,
    sobre toda a receita do ano (aproximacao anual: usa o faturamento anual
    como RBT12 de todos os meses).
    """
    for limite, nominal, deducao in _FAIXAS_SIMPLES[anexo]:
        if rbt12 <= limite:
            return max(0.0, rbt12 * nominal / 100 - deducao)
    raise ValueError(f"RBT12 {rbt12} excede o limite do Simples Nacional")


def _calc_simples(
    faturamento: float,
    setor: Literal["comércio", "serviços", "indústria"],
    folha: float | None,
) -> tuple[bool, float | None, float | None, str | None]:
    if faturamento > _LIMITE_SIMPLES:
        return (
            False,
            None,
            None,
            "Faturamento excede o limite anual do Simples Nacional (R$ 4,8 milhoes).",
        )

    if setor == "comércio":
        anexo = "I"
    elif setor == "indústria":
        anexo = "II"
    else:  # serviços: Anexo III ou V conforme Fator R (folha / faturamento >= 0.28)
        fator_r = (folha or 0) / faturamento if faturamento > 0 else 0
        anexo = "III" if fator_r >= 0.28 else "V"

    imposto = _imposto_simples(faturamento, anexo)
    alíquota = round(imposto / faturamento * 100, 2)
    return True, alíquota, imposto, None


def _calc_lucro_presumido(
    faturamento: float, setor: Literal["comércio", "serviços", "indústria"]
) -> tuple[bool, float | None, float | None, str | None]:
    if faturamento > _LIMITE_LUCRO_PRESUMIDO:
        return (
            False,
            None,
            None,
            "Faturamento excede o limite anual do Lucro Presumido (R$ 78 milhoes).",
        )
    # Presuncao de lucro (Lei 9.249/1995, arts. 15 e 20): IRPJ 8% comercio/industria
    # e 32% servicos; CSLL 12% comercio/industria e 32% servicos.
    if setor == "serviços":
        presuncao_irpj = 0.32
        presuncao_csll = 0.32
    else:
        presuncao_irpj = 0.08
        presuncao_csll = 0.12
    base_irpj = faturamento * presuncao_irpj
    irpj = base_irpj * 0.15
    # Adicional de IRPJ: 10% sobre o lucro presumido que excede R$ 60 mil/trimestre.
    adicional = max(0.0, base_irpj - _LIMITE_ADICIONAL_IRPJ_ANUAL) * 0.10
    csll = faturamento * presuncao_csll * 0.09
    # PIS+COFINS regime cumulativo
    pis_cofins = faturamento * 0.0365
    # ISS estimado (serviços) ou ICMS estimado (comércio/indústria)
    if setor == "serviços":
        outros = faturamento * 0.05  # ISS medio
    else:
        outros = faturamento * 0.12  # ICMS medio com beneficios
    total = irpj + adicional + csll + pis_cofins + outros
    aliquota_efetiva = total / faturamento * 100
    return True, aliquota_efetiva, total, None


def _calc_lucro_real_simplificado(
    faturamento: float, setor: Literal["comércio", "serviços", "indústria"]
) -> tuple[bool, float | None, float | None, str | None]:
    # Estimativa muito grosseira: margem operacional 15% (lucro liquido)
    margem = 0.15
    lucro = faturamento * margem
    irpj = lucro * 0.15
    adicional = max(0.0, lucro - 240_000) * 0.10
    csll = lucro * 0.09
    pis_cofins = faturamento * 0.0925  # não-cumulativo
    if setor == "serviços":
        outros = faturamento * 0.05
    else:
        outros = faturamento * 0.12
    total = irpj + adicional + csll + pis_cofins + outros
    aliquota_efetiva = total / faturamento * 100
    return True, aliquota_efetiva, total, None


def _calc_mei(
    faturamento: float, setor: Literal["comércio", "serviços", "indústria"]
) -> tuple[bool, float | None, float | None, str | None]:
    if faturamento > _LIMITE_MEI:
        return False, None, None, "Faturamento excede o limite anual do MEI (R$ 81 mil)."
    # Valor mensal MEI 2025 ~ R$ 75 comércio/indústria, R$ 80 serviços
    mensal = 80 if setor == "serviços" else 75
    total = mensal * 12
    aliquota_efetiva = total / faturamento * 100 if faturamento else 0
    return True, aliquota_efetiva, total, None


def compare_tax_regimes(
    faturamento_anual: float,
    setor: Literal["comércio", "serviços", "indústria"],
    folha_pagamento_anual: float | None = None,
) -> TaxRegimeComparison:
    """
    Compara regimes tributarios brasileiros (MEI, Simples, Lucro Presumido, Lucro Real).

    Estimativa rápida baseada em tabelas publicas vigentes. NAO substitui parecer
    de contador. Util para direcionamento em decisões de planejamento tributário.

    Args:
        faturamento_anual: Receita bruta anual em reais.
        setor: Setor da empresa (impacta anexo do Simples e presuncoes do LP).
        folha_pagamento_anual: Folha anual em reais. Importante para Fator R no Simples
            (serviços): se folha/faturamento >= 28%, usa Anexo III (mais barato).

    Returns:
        TaxRegimeComparison com opcoes avaliadas, melhor regime e economia estimada.

    Exemplo:
        resultado = compare_tax_regimes(
            faturamento_anual=500_000,
            setor="serviços",
            folha_pagamento_anual=180_000,
        )
        print(resultado.melhor_opcao)  # "simples_nacional"
        print(resultado.economia_anual_vs_pior)  # economia vs pior opção
    """
    if faturamento_anual <= 0:
        raise ValueError("faturamento_anual deve ser positivo")

    opcoes_calc = [
        ("mei", _calc_mei(faturamento_anual, setor)),
        ("simples_nacional", _calc_simples(faturamento_anual, setor, folha_pagamento_anual)),
        ("lucro_presumido", _calc_lucro_presumido(faturamento_anual, setor)),
        ("lucro_real", _calc_lucro_real_simplificado(faturamento_anual, setor)),
    ]

    opcoes: list[TaxRegimeOption] = []
    for regime, (aplicavel, alíquota, imposto, motivo) in opcoes_calc:
        pros: list[str] = []
        contras: list[str] = []
        if regime == "mei":
            pros = ["Tributacao fixa mensal", "Burocracia minima"]
            contras = ["Limite baixo de faturamento", "Restrito a algumas atividades"]
        elif regime == "simples_nacional":
            pros = ["Recolhimento unificado (DAS)", "Aliquotas progressivas"]
            contras = ["Limite de R$ 4,8 mi anual", "Limitacoes em serviços especificos"]
        elif regime == "lucro_presumido":
            pros = ["Calculo simples", "Aproveitamento de margens altas"]
            contras = ["PIS/COFINS cumulativos", "Pode pagar imposto sobre lucro inexistente"]
        else:
            pros = [
                "Sem teto de faturamento",
                "PIS/COFINS não-cumulativos com creditos",
                "Imposto sobre lucro real",
            ]
            contras = [
                "Burocracia alta (escrituracao completa)",
                "Custo contabil maior",
                "Antecipacoes mensais",
            ]
        opcoes.append(
            TaxRegimeOption(
                regime=regime,
                aplicavel=aplicavel,
                motivo_inaplicavel=motivo,
                aliquota_efetiva_estimada=alíquota,
                imposto_anual_estimado=imposto,
                pros=pros,
                contras=contras,
            )
        )

    aplicaveis = [o for o in opcoes if o.aplicavel and o.imposto_anual_estimado is not None]
    if not aplicaveis:
        raise RuntimeError("Nenhum regime aplicavel ao cenário fornecido")

    aplicaveis.sort(key=lambda o: o.imposto_anual_estimado or float("inf"))
    melhor = aplicaveis[0]
    pior_aplicavel = aplicaveis[-1]
    economia = (pior_aplicavel.imposto_anual_estimado or 0) - (melhor.imposto_anual_estimado or 0)

    obs = (
        "Estimativa simplificada usando tabelas publicas vigentes em 2025. "
        "Simples Nacional: aliquota efetiva dos Anexos I/II/III/V com parcela a deduzir "
        "(LC 123/2006, art. 18, par. 1o-A), tomando o faturamento anual como RBT12. "
        "Lucro Presumido: presuncoes de 8%/32% (IRPJ) e 12%/32% (CSLL) com adicional de "
        "IRPJ de 10% acima de R$ 240 mil/ano de lucro presumido. "
        "Considera presuncoes médias de ICMS/ISS. Não inclui beneficios estaduais nem "
        "regimes especiais. Consulte contador para decisão final."
    )

    return TaxRegimeComparison(
        cenario_faturamento_anual=faturamento_anual,
        cenario_setor=setor,
        folha_pagamento_anual=folha_pagamento_anual,
        opcoes=[*aplicaveis, *(o for o in opcoes if not o.aplicavel)],
        melhor_opcao=melhor.regime,
        economia_anual_vs_pior=economia,
        observacoes=obs,
    )
