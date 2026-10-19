"""Fail-closed PEP 440 interpreter compatibility check for project metadata."""

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


def validated_python_requirement(pyproject: dict, runtime_version: str) -> str:
    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise ValueError("PYPROJECT_PROJECT_MISSING")
    requirement = project.get("requires-python")
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("REQUIRES_PYTHON_MISSING")
    try:
        constraint = SpecifierSet(requirement)
    except InvalidSpecifier as exc:
        raise ValueError("REQUIRES_PYTHON_INVALID") from exc
    try:
        runtime = Version(runtime_version)
    except InvalidVersion as exc:
        raise ValueError("RUNTIME_PYTHON_VERSION_INVALID") from exc
    if not constraint.contains(runtime):
        raise RuntimeError(f"PYTHON_RUNTIME_UNSUPPORTED: {runtime} not in {requirement}")
    return requirement
