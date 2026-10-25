"""Known synthetic source bytes and explicitly simulated WORK domain decisions.

This is NOT runtime HUMAN provisioning or a path for real CASE data.
"""
from datetime import date, datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid5

from lukart_work.contracts.messages import Snapshot, SnapshotMember, SourceDocument
from lukart_work.domain.models import (
    Actor, Case, Decision, Evidence, Fact, LegalRule, LegalSource, Locator,
    Provenance, Ref, SnapshotTarget, SourceAnchor, TimeRange, VersionPin,
)
from lukart_work.validation.rules import digest, ref
from .service import CATALOGUE, CaseView, Intake, document_pin

NAMESPACE = UUID("9bf1600e-0f80-4c67-80ee-52abe43237df")
NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)
DEMO_TEXT = {
    "payment": {"principal": "Kwota z umowy demonstracyjnej wynosi 100 jednostek testowych.",
                "due_date": "Umowa demonstracyjna wskazuje datę wykonania 2026-10-01.",
                "destination": "Płatność ma nastąpić do kasy demonstracyjnej Alfa."},
    "complaint": {"defect": "Protokół demonstracyjny opisuje pękniętą osłonę urządzenia testowego.",
                  "remedy": "Wybrane żądanie demonstracyjne obejmuje wymianę osłony."},
    "reply": {"incoming": "Demonstracyjne wezwanie doręczono w dniu 2026-10-10.",
              "position": "Stanowisko demonstracyjne kwestionuje całość żądania."},
}


def synthetic_case(document_type="payment"):
    if document_type not in CATALOGUE:
        raise ValueError("DOCUMENT_TYPE_UNSUPPORTED")
    def uid(name):
        return uuid5(NAMESPACE, f"{document_type}/{name}")
    actor = Actor(id=uid("simulated-human"), kind="HUMAN")
    pin = VersionPin(id="synthetic-demo", version="1.0.0", content_hash=digest("synthetic-demo-v1"))
    provenance = Provenance(actor=actor, operation_id=uid("fixture"), method="MANUAL",
        inputs=(), anchors=(), rationale="Synthetic fixture only; no real HUMAN decision occurred")
    def common(name):
        return dict(schema_version="1.0.0", id=uid(name), tenant_id=uid("tenant"),
            case_id=uid("case"), revision=1, previous_hash=None, created_at=NOW,
            recorded_at=NOW, provenance=provenance)
    case = Case(**common("case"), kind="Case", status="OPEN", title="Demonstration only",
        jurisdiction="SYNTHETIC", owner_id=actor.id, retention_policy=pin)
    records, sources, blobs, fields = [case], [], {}, {}
    def source_for(name, text):
        content = text.encode("utf-8")
        content_hash = sha256(content).hexdigest()
        source = SourceDocument(id=uid(f"source-{name}"), tenant_id=case.tenant_id,
            case_id=case.id, content_hash=content_hash, media_type="text/plain",
            byte_length=len(content), object_key=f"synthetic/{name}", received_at=NOW,
            actor=actor, retention_policy=pin)
        sources.append(source)
        blobs[str(source.id)] = content
        return SourceAnchor(document_id=source.id, document_hash=content_hash,
            locator=Locator(unit="BYTE_RANGE", value=f"0:{len(content)}", fragment_hash=content_hash))
    def decision(name, target, kind):
        return Decision(**common(name), kind="Decision", status="RECORDED", decision_type=kind,
            targets=(target,), outcome="ACCEPT", rationale="Simulated synthetic fixture decision",
            decided_by=actor)
    for name, text in DEMO_TEXT[document_type].items():
        anchor = source_for(name, text)
        evidence = Evidence(**common(f"evidence-{name}"), kind="Evidence", status="ACCEPTED",
            evidence_type="DOCUMENT", description=f"Synthetic {name}", source=anchor, authenticity="VERIFIED")
        reviewed = Fact(**{**common(f"fact-{name}"), "provenance": provenance.model_copy(update={"anchors": (anchor,)})},
            kind="Fact", status="REVIEWED", statement=text, support="SOURCE_BACKED", evidence=(ref(evidence),),
            subjects=(), key_fact=True)
        approval = decision(f"accept-{name}", ref(reviewed), "FACT_ACCEPTANCE")
        fact = reviewed.model_copy(update={"revision": 2, "previous_hash": digest(reviewed),
            "status": "CONFIRMED", "acceptance": ref(approval)})
        records.extend((evidence, reviewed, fact, approval))
        fields[name] = ref(fact)
    legal_text = "Reguła demonstracyjna: treść pisma musi odpowiadać wskazanemu żądaniu."
    anchor = source_for("legal", legal_text)
    period = TimeRange(start=date(2026, 1, 1), end=date(2026, 12, 31))
    legal_pin = VersionPin(id="synthetic-legal-source", version="1.0.0", content_hash=anchor.document_hash)
    legal = LegalSource(**common("legal"), kind="LegalSource", status="VERIFIED", registry_pin=legal_pin,
        jurisdiction="SYNTHETIC", source_type="USER_MATERIAL", title="Reguła demonstracyjna",
        identifier="SYNTHETIC-RULE-1", effective_period=period, retrieved_at=NOW,
        source_uri="https://example.invalid/synthetic-rule", content_hash=anchor.document_hash,
        authority_level="INFORMATIONAL", anchor=anchor)
    rule_ref = Ref(kind="LegalRule", id=uid("rule"), revision=1)
    interpretation = decision("interpretation", rule_ref, "INTERPRETATION")
    reviewed_rule = LegalRule(**common("rule"), kind="LegalRule", status="REVIEWED", rule_type="INTERPRETIVE",
        statement=legal_text, sources=(ref(legal),), jurisdiction="SYNTHETIC", effective_period=period,
        applicable_document_types=(document_pin(document_type),), interpretation="SETTLED")
    rule = reviewed_rule.model_copy(update={"revision": 2, "previous_hash": digest(reviewed_rule),
        "status": "ACTIVE", "review_decision": ref(interpretation)})
    records.extend((legal, reviewed_rule, rule, interpretation))
    heads = {}
    for item in records:
        key = (item.kind, item.id)
        if key not in heads or item.revision > heads[key].revision:
            heads[key] = ref(item)
    snapshot = Snapshot(schema_version="1.0.0", id=uid("snapshot"), tenant_id=case.tenant_id,
        case_id=case.id, case_sequence=len(records), created_at=NOW,
        members=tuple(SnapshotMember(ref=ref(item), content_hash=digest(item)) for item in records),
        heads=tuple(heads.values()), sources=tuple(sources),
        knowledge_pins=(pin,), rule_set=pin, policy=pin)
    acceptance = Decision(**common("snapshot-acceptance"), kind="Decision", status="RECORDED",
        decision_type="SNAPSHOT_ACCEPTANCE", targets=(ref(case),), outcome="ACCEPT",
        rationale="Simulated fixture snapshot acceptance; not a real HUMAN decision", decided_by=actor,
        snapshot_target=SnapshotTarget(tenant_id=case.tenant_id, case_id=case.id,
            snapshot_id=snapshot.id, snapshot_hash=digest(snapshot)))
    intake = Intake(document_type, date(2026, 10, 23), "Podmiot demonstracyjny Alfa",
        "Podmiot demonstracyjny Beta", "Miejscowość demonstracyjna",
        {"payment": "Proszę o zapłatę kwoty wskazanej poniżej.",
         "complaint": "Proszę o usunięcie opisanej poniżej wady.",
         "reply": "Przedstawiam poniższe stanowisko wobec wezwania."}[document_type], fields, ref(rule))
    return CaseView(snapshot, tuple(records), blobs, acceptance), intake
