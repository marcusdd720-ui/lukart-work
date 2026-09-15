# 01 — Katalog encji i pól

Kontrakt normatywny: lukart_work/domain/models.py. Schematy JSON są eksportem. Wszystkie encje dziedziczą Entity; wspólne value objects są rozwinięte w $defs każdego schematu. Pole wymagane musi wystąpić; typ nullable może jawnie zawierać null. Kolekcje są wymagane także wtedy, gdy dopuszczają pustą listę.

Każda rewizja jest niezmienna. Aktualizacja to nowa rewizja z previous_hash, CAS i audytem. Ownership: tenant_id + case_id; Case.id = case_id. Pełne wymagania wykraczające poza schemat: docs/01-specification.md.

## Case

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Case", "type": "string"}` | tak |
| status | `{"enum": ["OPEN", "SUSPENDED", "CLOSED", "ARCHIVED"], "type": "string"}` | tak |
| title | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| jurisdiction | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| owner_id | `{"format": "uuid", "type": "string"}` | tak |
| retention_policy | `{"$ref": "#/$defs/VersionPin"}` | tak |

Stan początkowy: `OPEN`. Dozwolone przejścia:

`OPEN → SUSPENDED`; `SUSPENDED → OPEN`; `OPEN → CLOSED`; `SUSPENDED → CLOSED`; `CLOSED → OPEN`; `CLOSED → ARCHIVED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Party

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Party", "type": "string"}` | tak |
| status | `{"enum": ["UNVERIFIED", "VERIFIED", "DISPUTED", "INACTIVE"], "type": "string"}` | tak |
| party_type | `{"enum": ["PERSON", "ORGANIZATION", "UNKNOWN"], "type": "string"}` | tak |
| display_name | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| address | `{"anyOf": [{"$ref": "#/$defs/Address"}, {"type": "null"}]}` | nie |
| identity_evidence | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| verification_decision | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `UNVERIFIED`. Dozwolone przejścia:

`UNVERIFIED → VERIFIED`; `UNVERIFIED → DISPUTED`; `VERIFIED → DISPUTED`; `DISPUTED → VERIFIED`; `VERIFIED → INACTIVE`; `UNVERIFIED → INACTIVE`; `DISPUTED → INACTIVE`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Institution

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Institution", "type": "string"}` | tak |
| status | `{"enum": ["UNVERIFIED", "VERIFIED", "INACTIVE"], "type": "string"}` | tak |
| institution_type | `{"enum": ["COURT", "AUTHORITY", "OMBUDSMAN", "OTHER", "UNKNOWN"], "type": "string"}` | tak |
| name | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| jurisdiction | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| address | `{"anyOf": [{"$ref": "#/$defs/Address"}, {"type": "null"}]}` | nie |
| registry_identifier | `{"anyOf": [{"maxLength": 20000, "minLength": 1, "type": "string"}, {"type": "null"}]}` | nie |

Stan początkowy: `UNVERIFIED`. Dozwolone przejścia:

`UNVERIFIED → VERIFIED`; `VERIFIED → UNVERIFIED`; `VERIFIED → INACTIVE`; `UNVERIFIED → INACTIVE`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Proceeding

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Proceeding", "type": "string"}` | tak |
| status | `{"enum": ["PLANNED", "PENDING", "STAYED", "CONCLUDED", "CANCELLED"], "type": "string"}` | tak |
| proceeding_type | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| institution | `{"$ref": "#/$defs/Ref"}` | tak |
| participants | `{"items": {"$ref": "#/$defs/Participation"}, "minItems": 1, "type": "array"}` | tak |
| reference_number | `{"anyOf": [{"maxLength": 20000, "minLength": 1, "type": "string"}, {"type": "null"}]}` | nie |
| parent_proceeding | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `PLANNED`. Dozwolone przejścia:

`PLANNED → PENDING`; `PLANNED → CANCELLED`; `PENDING → STAYED`; `STAYED → PENDING`; `PENDING → CONCLUDED`; `STAYED → CONCLUDED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Filing

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Filing", "type": "string"}` | tak |
| status | `{"enum": ["PLANNED", "PREPARING", "READY", "SUBMITTED", "ACKNOWLEDGED", "WITHDRAWN"], "type": "string"}` | tak |
| document_type | `{"$ref": "#/$defs/VersionPin"}` | tak |
| direction | `{"enum": ["INCOMING", "OUTGOING"], "type": "string"}` | tak |
| proceeding | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |
| recipient | `{"$ref": "#/$defs/Ref"}` | tak |
| authors | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| submitted_at | `{"anyOf": [{"format": "date-time", "type": "string"}, {"type": "null"}]}` | nie |
| submission_receipt | `{"anyOf": [{"$ref": "#/$defs/SourceAnchor"}, {"type": "null"}]}` | nie |

Stan początkowy: `PLANNED`. Dozwolone przejścia:

`PLANNED → PREPARING`; `PREPARING → READY`; `READY → PREPARING`; `READY → SUBMITTED`; `SUBMITTED → ACKNOWLEDGED`; `SUBMITTED → WITHDRAWN`; `ACKNOWLEDGED → WITHDRAWN`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Fact

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Fact", "type": "string"}` | tak |
| status | `{"enum": ["CANDIDATE", "EXTRACTED", "REVIEWED", "CONFIRMED", "DISPUTED", "REJECTED"], "type": "string"}` | tak |
| statement | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| support | `{"enum": ["SOURCE_BACKED", "INFERRED", "UNSUPPORTED"], "type": "string"}` | tak |
| evidence | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| subjects | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| event_date | `{"anyOf": [{"format": "date", "type": "string"}, {"type": "null"}]}` | nie |
| amount | `{"anyOf": [{"$ref": "#/$defs/Money"}, {"type": "null"}]}` | nie |
| key_fact | `{"type": "boolean"}` | tak |
| acceptance | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `CANDIDATE`. Dozwolone przejścia:

`CANDIDATE → EXTRACTED`; `CANDIDATE → REVIEWED`; `EXTRACTED → REVIEWED`; `REVIEWED → CONFIRMED`; `REVIEWED → DISPUTED`; `CONFIRMED → DISPUTED`; `DISPUTED → REVIEWED`; `CANDIDATE → REJECTED`; `EXTRACTED → REJECTED`; `REVIEWED → REJECTED`; `DISPUTED → REJECTED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Evidence

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Evidence", "type": "string"}` | tak |
| status | `{"enum": ["REGISTERED", "REVIEWED", "ACCEPTED", "CHALLENGED", "EXCLUDED"], "type": "string"}` | tak |
| evidence_type | `{"enum": ["DOCUMENT", "TESTIMONY", "IMAGE", "RECORDING", "OTHER"], "type": "string"}` | tak |
| description | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| source | `{"$ref": "#/$defs/SourceAnchor"}` | tak |
| authenticity | `{"enum": ["UNKNOWN", "VERIFIED", "DISPUTED"], "type": "string"}` | tak |
| submitted_in | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `REGISTERED`. Dozwolone przejścia:

`REGISTERED → REVIEWED`; `REVIEWED → ACCEPTED`; `REVIEWED → CHALLENGED`; `ACCEPTED → CHALLENGED`; `CHALLENGED → REVIEWED`; `REGISTERED → EXCLUDED`; `REVIEWED → EXCLUDED`; `CHALLENGED → EXCLUDED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Issue

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Issue", "type": "string"}` | tak |
| status | `{"enum": ["IDENTIFIED", "ANALYZING", "UNRESOLVED", "RESOLVED", "CLOSED"], "type": "string"}` | tak |
| question | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| facts | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| rules | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| resolution | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `IDENTIFIED`. Dozwolone przejścia:

`IDENTIFIED → ANALYZING`; `ANALYZING → UNRESOLVED`; `UNRESOLVED → ANALYZING`; `ANALYZING → RESOLVED`; `RESOLVED → ANALYZING`; `RESOLVED → CLOSED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## LegalSource

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "LegalSource", "type": "string"}` | tak |
| status | `{"enum": ["REGISTERED", "VERIFIED", "SUPERSEDED", "RETRACTED"], "type": "string"}` | tak |
| registry_pin | `{"$ref": "#/$defs/VersionPin"}` | tak |
| jurisdiction | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| source_type | `{"enum": ["LAW", "CASE_LAW", "OFFICIAL_GUIDANCE", "DOCTRINE", "SECONDARY_SOURCE", "USER_MATERIAL"], "type": "string"}` | tak |
| title | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| identifier | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| effective_period | `{"$ref": "#/$defs/TimeRange"}` | tak |
| retrieved_at | `{"format": "date-time", "type": "string"}` | tak |
| source_uri | `{"pattern": "^https?://[^\\s]+$", "type": "string"}` | tak |
| content_hash | `{"pattern": "^[0-9a-f]{64}$", "type": "string"}` | tak |
| authority_level | `{"enum": ["BINDING", "PERSUASIVE", "INFORMATIONAL", "UNKNOWN"], "type": "string"}` | tak |
| anchor | `{"$ref": "#/$defs/SourceAnchor"}` | tak |

Stan początkowy: `REGISTERED`. Dozwolone przejścia:

`REGISTERED → VERIFIED`; `VERIFIED → SUPERSEDED`; `REGISTERED → RETRACTED`; `VERIFIED → RETRACTED`; `SUPERSEDED → RETRACTED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## LegalRule

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "LegalRule", "type": "string"}` | tak |
| status | `{"enum": ["PROPOSED", "REVIEWED", "ACTIVE", "SUPERSEDED", "WITHDRAWN"], "type": "string"}` | tak |
| rule_type | `{"enum": ["SUBSTANTIVE", "PROCEDURAL", "INTERPRETIVE"], "type": "string"}` | tak |
| statement | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| sources | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| jurisdiction | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| effective_period | `{"$ref": "#/$defs/TimeRange"}` | tak |
| applicable_document_types | `{"items": {"$ref": "#/$defs/VersionPin"}, "type": "array"}` | tak |
| requirement | `{"anyOf": [{"$ref": "#/$defs/Requirement"}, {"type": "null"}]}` | nie |
| interpretation | `{"enum": ["SETTLED", "DISPUTED", "UNKNOWN"], "type": "string"}` | tak |
| review_decision | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `PROPOSED`. Dozwolone przejścia:

`PROPOSED → REVIEWED`; `REVIEWED → ACTIVE`; `ACTIVE → SUPERSEDED`; `PROPOSED → WITHDRAWN`; `REVIEWED → WITHDRAWN`; `ACTIVE → WITHDRAWN`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Claim

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Claim", "type": "string"}` | tak |
| status | `{"enum": ["PROPOSED", "REVIEWED", "ADOPTED", "DISPUTED", "WITHDRAWN", "RESOLVED"], "type": "string"}` | tak |
| claim_type | `{"enum": ["ASSERTION", "REMEDY"], "type": "string"}` | tak |
| statement | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| claimant | `{"$ref": "#/$defs/Ref"}` | tak |
| issues | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| facts | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| rules | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| support | `{"enum": ["SOURCE_BACKED", "INFERRED", "UNSUPPORTED"], "type": "string"}` | tak |
| amount | `{"anyOf": [{"$ref": "#/$defs/Money"}, {"type": "null"}]}` | nie |
| adoption | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `PROPOSED`. Dozwolone przejścia:

`PROPOSED → REVIEWED`; `REVIEWED → ADOPTED`; `ADOPTED → DISPUTED`; `DISPUTED → REVIEWED`; `ADOPTED → RESOLVED`; `DISPUTED → RESOLVED`; `PROPOSED → WITHDRAWN`; `REVIEWED → WITHDRAWN`; `ADOPTED → WITHDRAWN`; `DISPUTED → WITHDRAWN`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Defence

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Defence", "type": "string"}` | tak |
| status | `{"enum": ["PROPOSED", "REVIEWED", "ADOPTED", "WITHDRAWN", "RESOLVED"], "type": "string"}` | tak |
| claim | `{"$ref": "#/$defs/Ref"}` | tak |
| party | `{"$ref": "#/$defs/Ref"}` | tak |
| statement | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| facts | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| rules | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| adoption | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `PROPOSED`. Dozwolone przejścia:

`PROPOSED → REVIEWED`; `REVIEWED → ADOPTED`; `ADOPTED → RESOLVED`; `PROPOSED → WITHDRAWN`; `REVIEWED → WITHDRAWN`; `ADOPTED → WITHDRAWN`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Argument

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Argument", "type": "string"}` | tak |
| status | `{"enum": ["PROPOSED", "REVIEWED", "ADOPTED", "CHALLENGED", "WITHDRAWN"], "type": "string"}` | tak |
| target | `{"$ref": "#/$defs/Ref"}` | tak |
| polarity | `{"enum": ["SUPPORTS", "OPPOSES"], "type": "string"}` | tak |
| conclusion | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| premises | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| rules | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| support | `{"enum": ["SOURCE_BACKED", "INFERRED", "UNSUPPORTED"], "type": "string"}` | tak |
| assessments | `{"items": {"$ref": "#/$defs/Assessment"}, "type": "array"}` | tak |

Stan początkowy: `PROPOSED`. Dozwolone przejścia:

`PROPOSED → REVIEWED`; `REVIEWED → ADOPTED`; `ADOPTED → CHALLENGED`; `CHALLENGED → REVIEWED`; `PROPOSED → WITHDRAWN`; `REVIEWED → WITHDRAWN`; `ADOPTED → WITHDRAWN`; `CHALLENGED → WITHDRAWN`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## CounterArgument

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "CounterArgument", "type": "string"}` | tak |
| status | `{"enum": ["IDENTIFIED", "REVIEWED", "ANSWERED", "UNRESOLVED", "DISMISSED"], "type": "string"}` | tak |
| target_argument | `{"$ref": "#/$defs/Ref"}` | tak |
| statement | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| premises | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| support | `{"enum": ["SOURCE_BACKED", "INFERRED", "UNSUPPORTED"], "type": "string"}` | tak |
| response_argument | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `IDENTIFIED`. Dozwolone przejścia:

`IDENTIFIED → REVIEWED`; `REVIEWED → ANSWERED`; `REVIEWED → UNRESOLVED`; `UNRESOLVED → REVIEWED`; `REVIEWED → DISMISSED`; `ANSWERED → UNRESOLVED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Request

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Request", "type": "string"}` | tak |
| status | `{"enum": ["PROPOSED", "REVIEWED", "APPROVED", "WITHDRAWN", "RESOLVED"], "type": "string"}` | tak |
| filing | `{"$ref": "#/$defs/Ref"}` | tak |
| request_type | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| text | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| claims | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| evidence | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| approval | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |
| amount | `{"anyOf": [{"$ref": "#/$defs/Money"}, {"type": "null"}]}` | nie |

Stan początkowy: `PROPOSED`. Dozwolone przejścia:

`PROPOSED → REVIEWED`; `REVIEWED → APPROVED`; `APPROVED → RESOLVED`; `PROPOSED → WITHDRAWN`; `REVIEWED → WITHDRAWN`; `APPROVED → WITHDRAWN`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Deadline

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Deadline", "type": "string"}` | tak |
| status | `{"enum": ["UNKNOWN", "CALCULATED", "VERIFIED", "SATISFIED", "EXPIRED", "CANCELLED"], "type": "string"}` | tak |
| proceeding | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |
| filing | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |
| trigger | `{"$ref": "#/$defs/Ref"}` | tak |
| rules | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| due_at | `{"anyOf": [{"format": "date-time", "type": "string"}, {"type": "null"}]}` | nie |
| timezone | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| calendar_pin | `{"$ref": "#/$defs/VersionPin"}` | tak |
| computation_trace | `{"items": {"maxLength": 20000, "minLength": 1, "type": "string"}, "type": "array"}` | tak |
| satisfaction | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `UNKNOWN`. Dozwolone przejścia:

`UNKNOWN → CALCULATED`; `CALCULATED → VERIFIED`; `VERIFIED → CALCULATED`; `CALCULATED → UNKNOWN`; `VERIFIED → SATISFIED`; `VERIFIED → EXPIRED`; `UNKNOWN → CANCELLED`; `CALCULATED → CANCELLED`; `VERIFIED → CANCELLED`; `EXPIRED → SATISFIED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Risk

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Risk", "type": "string"}` | tak |
| status | `{"enum": ["OPEN", "MITIGATING", "ACCEPTED", "RESOLVED"], "type": "string"}` | tak |
| category | `{"enum": ["FACTUAL", "EVIDENTIARY", "LEGAL", "PROCEDURAL", "PRIVACY", "OPERATIONAL"], "type": "string"}` | tak |
| description | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| severity | `{"enum": ["INFO", "WARNING", "ERROR", "BLOCKER", "CRITICAL"], "type": "string"}` | tak |
| affected | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| mitigation | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |
| acceptance | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `OPEN`. Dozwolone przejścia:

`OPEN → MITIGATING`; `MITIGATING → ACCEPTED`; `OPEN → ACCEPTED`; `OPEN → RESOLVED`; `MITIGATING → RESOLVED`; `ACCEPTED → OPEN`; `RESOLVED → OPEN`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Citation

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Citation", "type": "string"}` | tak |
| status | `{"enum": ["PROPOSED", "BOUND", "VERIFIED", "INVALID"], "type": "string"}` | tak |
| source | `{"$ref": "#/$defs/Ref"}` | tak |
| locator | `{"$ref": "#/$defs/Locator"}` | tak |
| supported | `{"$ref": "#/$defs/Ref"}` | tak |
| quotation | `{"anyOf": [{"maxLength": 20000, "minLength": 1, "type": "string"}, {"type": "null"}]}` | nie |

Stan początkowy: `PROPOSED`. Dozwolone przejścia:

`PROPOSED → BOUND`; `BOUND → VERIFIED`; `BOUND → INVALID`; `VERIFIED → INVALID`; `INVALID → BOUND`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## DocumentPlan

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "DocumentPlan", "type": "string"}` | tak |
| status | `{"enum": ["PROPOSED", "REVIEWED", "APPROVED", "SUPERSEDED", "REJECTED"], "type": "string"}` | tak |
| filing | `{"$ref": "#/$defs/Ref"}` | tak |
| input_snapshot_id | `{"format": "uuid", "type": "string"}` | tak |
| input_snapshot_hash | `{"pattern": "^[0-9a-f]{64}$", "type": "string"}` | tak |
| objectives | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| recipient | `{"$ref": "#/$defs/Ref"}` | tak |
| position_scope | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| argument_order | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| evidence | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| section_order | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| approval | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `PROPOSED`. Dozwolone przejścia:

`PROPOSED → REVIEWED`; `REVIEWED → APPROVED`; `PROPOSED → REJECTED`; `REVIEWED → REJECTED`; `APPROVED → SUPERSEDED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Section

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Section", "type": "string"}` | tak |
| status | `{"enum": ["PLANNED", "READY", "RETIRED"], "type": "string"}` | tak |
| filing | `{"$ref": "#/$defs/Ref"}` | tak |
| section_type | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| title | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| arguments | `{"items": {"$ref": "#/$defs/Ref"}, "type": "array"}` | tak |
| contract | `{"$ref": "#/$defs/SectionContract"}` | tak |

Stan początkowy: `PLANNED`. Dozwolone przejścia:

`PLANNED → READY`; `READY → RETIRED`; `PLANNED → RETIRED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Draft

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Draft", "type": "string"}` | tak |
| status | `{"enum": ["PLANNED", "GENERATED", "VALIDATED", "APPROVED", "RENDERED", "CERTIFIED"], "type": "string"}` | tak |
| plan | `{"$ref": "#/$defs/Ref"}` | tak |
| snapshot_id | `{"format": "uuid", "type": "string"}` | tak |
| snapshot_hash | `{"pattern": "^[0-9a-f]{64}$", "type": "string"}` | tak |
| sections | `{"items": {"$ref": "#/$defs/SectionText"}, "type": "array"}` | tak |
| reproduction | `{"$ref": "#/$defs/ReproductionManifest"}` | tak |
| supersedes | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `PLANNED`. Dozwolone przejścia:

`PLANNED → GENERATED`; `GENERATED → VALIDATED`; `VALIDATED → APPROVED`; `APPROVED → RENDERED`; `RENDERED → CERTIFIED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## ValidationFinding

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "ValidationFinding", "type": "string"}` | tak |
| status | `{"enum": ["OPEN", "RESOLVED", "FALSE_POSITIVE"], "type": "string"}` | tak |
| run_id | `{"format": "uuid", "type": "string"}` | tak |
| target | `{"$ref": "#/$defs/Ref"}` | tak |
| target_hash | `{"pattern": "^[0-9a-f]{64}$", "type": "string"}` | tak |
| layer | `{"enum": ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10", "RENDER"], "type": "string"}` | tak |
| code | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| severity | `{"enum": ["INFO", "WARNING", "ERROR", "BLOCKER", "CRITICAL"], "type": "string"}` | tak |
| message | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| path | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| resolution | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `OPEN`. Dozwolone przejścia:

`OPEN → RESOLVED`; `OPEN → FALSE_POSITIVE`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.

## Decision

| Pole | Typ/schemat | Wymagane |
|---|---|---|
| schema_version | `{"const": "1.0.0", "type": "string"}` | tak |
| id | `{"format": "uuid", "type": "string"}` | tak |
| tenant_id | `{"format": "uuid", "type": "string"}` | tak |
| case_id | `{"format": "uuid", "type": "string"}` | tak |
| revision | `{"minimum": 1, "type": "integer"}` | tak |
| previous_hash | `{"anyOf": [{"pattern": "^[0-9a-f]{64}$", "type": "string"}, {"type": "null"}]}` | tak |
| created_at | `{"format": "date-time", "type": "string"}` | tak |
| recorded_at | `{"format": "date-time", "type": "string"}` | tak |
| provenance | `{"$ref": "#/$defs/Provenance"}` | tak |
| kind | `{"const": "Decision", "type": "string"}` | tak |
| status | `{"enum": ["PROPOSED", "RECORDED", "SUPERSEDED", "REVOKED"], "type": "string"}` | tak |
| decision_type | `{"enum": ["IDENTITY", "FACT_ACCEPTANCE", "STRATEGY", "REQUEST_APPROVAL", "INTERPRETATION", "PLAN_APPROVAL", "DOCUMENT_APPROVAL", "RISK_ACCEPTANCE", "FINDING_RESOLUTION", "SNAPSHOT_ACCEPTANCE", "CERTIFICATION"], "type": "string"}` | tak |
| targets | `{"items": {"$ref": "#/$defs/Ref"}, "minItems": 1, "type": "array"}` | tak |
| outcome | `{"enum": ["ACCEPT", "REJECT", "ABSTAIN"], "type": "string"}` | tak |
| rationale | `{"maxLength": 20000, "minLength": 1, "type": "string"}` | tak |
| decided_by | `{"$ref": "#/$defs/Actor"}` | tak |
| supersedes | `{"anyOf": [{"$ref": "#/$defs/Ref"}, {"type": "null"}]}` | nie |

Stan początkowy: `PROPOSED`. Dozwolone przejścia:

`PROPOSED → RECORDED`; `RECORDED → SUPERSEDED`; `RECORDED → REVOKED`.

Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.
