from copy import deepcopy

from .fixture import positive_fixture


def negative_payloads() -> tuple[tuple[str, dict], ...]:
    base = positive_fixture().model_dump(mode="python")

    missing_amount = deepcopy(base)
    missing_amount.pop("principal_amount_decimal")

    invalid_amount = deepcopy(base)
    invalid_amount["principal_amount_decimal"] = "-1.00"

    unknown_procedure = deepcopy(base)
    unknown_procedure["procedural_coverage_ref"] = "UNKNOWN"

    wrong_currency = deepcopy(base)
    wrong_currency["currency_pln"] = "EUR"

    return (
        ("missing_principal_amount_decimal", missing_amount),
        ("invalid_principal_amount_decimal", invalid_amount),
        ("unknown_procedural_coverage", unknown_procedure),
        ("wrong_currency", wrong_currency),
    )
