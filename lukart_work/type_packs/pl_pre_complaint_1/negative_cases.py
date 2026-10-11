from copy import deepcopy

from .fixture import positive_fixture


def negative_payloads() -> tuple[tuple[str, dict], ...]:
    base = positive_fixture().model_dump(mode="python")

    missing_defect = deepcopy(base)
    missing_defect.pop("documented_defect")

    blank_remedy = deepcopy(base)
    blank_remedy["requested_remedy"] = " "

    no_correspondence = deepcopy(base)
    no_correspondence["prior_correspondence"] = ()

    unknown_procedure = deepcopy(base)
    unknown_procedure["procedural_coverage_ref"] = "UNKNOWN"

    return (
        ("missing_documented_defect", missing_defect),
        ("blank_requested_remedy", blank_remedy),
        ("missing_prior_correspondence", no_correspondence),
        ("unknown_procedural_coverage", unknown_procedure),
    )
