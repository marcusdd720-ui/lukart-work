from copy import deepcopy

from .fixture import positive_fixture


def negative_payloads() -> tuple[tuple[str, dict], ...]:
    base = positive_fixture().model_dump(mode="python")

    blank_position = deepcopy(base)
    blank_position["response_position_human"] = " "

    invalid_amount = deepcopy(base)
    invalid_amount["asserted_amount_decimal"] = "-100.00"

    empty_items = deepcopy(base)
    empty_items["admitted_and_disputed_items"] = ()

    empty_evidence = deepcopy(base)
    empty_evidence["supporting_evidence"] = ()

    return (
        ("blank_response_position_human", blank_position),
        ("invalid_asserted_amount_decimal", invalid_amount),
        ("empty_admitted_and_disputed_items", empty_items),
        ("empty_supporting_evidence", empty_evidence),
    )
