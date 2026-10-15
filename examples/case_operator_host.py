"""Copy into trusted deployment configuration and bind the six required objects.

See docs/GENERATOR_PISM_OPERATOR_RUNBOOK.md. This unbound example deliberately
fails closed when invoked by operator_host. It contains no CASE, identity,
credentials, capability grants, document profile or invented approval.
"""
from functools import partial

from lukart_work.operator_config import build_operator as assemble_operator

# Bind approved repository, authority, case_profile, drafting_profiles, provider
# and package_profile in the administrator's copy, never in source documents.
build_operator = partial(assemble_operator)
