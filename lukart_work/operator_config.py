"""Explicit trusted CASE-host wiring; no provisioning, migrations or CASE writes."""
from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import TokenAuthority
from lukart_work.drafting.contracts import DraftingProfile
from lukart_work.drafting.manual_provider import ManualAttestedDraftingProvider
from lukart_work.finalization.contracts import FinalizationProfile, FinalPackageProfile
from lukart_work.operator import GeneratorPismOperator
from lukart_work.storage.objects import RetentionPolicies


def build_operator(
    *,
    repository: PostgresRepository,
    authority: TokenAuthority,
    case_profile: FinalizationProfile,
    drafting_profiles: dict[str, DraftingProfile],
    provider: ManualAttestedDraftingProvider,
    package_profile: FinalPackageProfile,
    ocr_config=None,
) -> GeneratorPismOperator:
    """Assemble existing components supplied by an administrator's trusted code.

    These checks catch incomplete wiring, not legal admission or authentication.
    The existing service boundaries remain authoritative for every operation.
    Construction opens no SQL connection and provisions no capabilities.
    """
    for value, expected in (
        (repository, PostgresRepository), (authority, TokenAuthority),
        (case_profile, FinalizationProfile),
        (provider, ManualAttestedDraftingProvider),
        (package_profile, FinalPackageProfile),
    ):
        if not isinstance(value, expected):
            raise ValueError("TRUSTED_CASE_COMPONENT_REQUIRED")
    if not repository.storage or not isinstance(repository.retention_policies, RetentionPolicies):
        raise ValueError("CASE_STORAGE_CONFIGURATION_REQUIRED")
    if not isinstance(drafting_profiles, dict) or not drafting_profiles:
        raise ValueError("EXPLICIT_DRAFTING_PROFILES_REQUIRED")
    for name, profile in drafting_profiles.items():
        if not isinstance(profile, DraftingProfile) or name != profile.profile:
            raise ValueError("DRAFTING_PROFILE_IDENTITY_MISMATCH")
        if profile.render_profile != case_profile.render_profile:
            raise ValueError("CASE_RENDER_PROFILE_MISMATCH")
        if any(getattr(profile, field) != getattr(provider, field) for field in (
            "provider", "model", "generator", "model_parameters_hash",
        )):
            raise ValueError("DRAFTING_PROVIDER_BINDING_MISMATCH")
    return GeneratorPismOperator(
        repository=repository, authority=authority, case_profile=case_profile,
        drafting_profiles=dict(drafting_profiles), provider=provider,
        package_profile=package_profile,
        ocr_config=ocr_config,
    )
