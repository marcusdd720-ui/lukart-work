"""Human review using the existing Core transaction, CAS, audit and outbox."""
from hashlib import sha256
import json
from uuid import UUID, uuid5
from pydantic import ValidationError
from lukart_work.core.service import CommandService, entity_from, safe_error
from lukart_work.core.requests import CoreRequest
from lukart_work.core.postgres import canonical
from lukart_work.domain import models as m
from lukart_work.contracts import messages as wire
from lukart_work.ingestion.service import IngestionService
from lukart_work.validation.rules import Violation, strict_json, digest, ref, walk
from .contracts import (FactEvidenceRequest, CandidateReviewRecord, FactEvidenceQuery,
                        EvidenceAssessment, FactAssessment, FactEvidenceMatrix)

CHANGES = {'MarkFactExtracted': ('Fact', 'EXTRACTED'), 'RejectFact': ('Fact', 'REJECTED'),
    'ReviewEvidence': ('Evidence', 'REVIEWED'), 'AcceptEvidence': ('Evidence', 'ACCEPTED'),
    'ChallengeEvidence': ('Evidence', 'CHALLENGED'), 'ExcludeEvidence': ('Evidence', 'EXCLUDED')}


class FactEvidenceService(CommandService):
    def _parse_request(self, raw):
        value = strict_json(raw)
        stack = [(value, 0)]
        while stack:
            item, depth = stack.pop()
            if depth > 64:
                raise Violation('SCHEMA_INVALID')
            if isinstance(item, dict): stack.extend((v, depth + 1) for v in item.values())
            elif isinstance(item, list): stack.extend((v, depth + 1) for v in item)
        return FactEvidenceRequest.model_validate_json(json.dumps(value, allow_nan=False))

    def _case_guard(self, request, principal, case):
        super()._case_guard(request, principal, case)
        if principal.actor.kind != 'HUMAN':
            raise Violation('FORBIDDEN')

    @staticmethod
    def _reviews(tx):
        reviews = sorted(tx.objects('candidate_review', CandidateReviewRecord),
            key=lambda r: (str(r.run_id), r.candidate_index, r.revision))
        previous = {}
        for review in reviews:
            key = (review.run_id, review.candidate_index)
            old = previous.get(key)
            if review.revision != (old.revision + 1 if old else 1) or review.previous_hash != (digest(old) if old else None):
                raise Violation('INVALID_HASH')
            if old and (old.disposition == 'ADMIT' or (old.source_id, old.result_hash) != (review.source_id, review.result_hash)):
                raise Violation('INVALID_HASH')
            previous[key] = review
        return tuple(reviews)

    def _extraction(self, tx, source_id, run_id, expected_hash):
        source = tx.object('source', source_id, wire.SourceDocument)
        tx.source_bytes(source_id)
        result = IngestionService(self.repository, self.authority)._read(tx, source, run_id)
        if digest(result) != expected_hash:
            raise Violation('INVALID_HASH')
        # Immutable legacy results can say EXTRACTED while a PDF page still needs OCR.
        if result.body.status != 'EXTRACTED' or 'OCR_REQUIRED' in result.body.warnings:
            raise Violation('GATE_DENIED')
        return result

    def _review_candidate(self, request, principal, tx, records, heads, now):
        data = request.data
        if not self.repository.storage:
            raise Violation('GATE_DENIED')
        if request.target is not None:
            raise Violation('SCHEMA_INVALID')
        result = self._extraction(tx, data.source_id, data.run_id, data.result_hash)
        if data.candidate_index >= len(result.body.candidates):
            raise Violation('BROKEN_REFERENCE')
        candidate = result.body.candidates[data.candidate_index]
        if candidate.kind not in ('FACT', 'EVIDENCE'):
            raise Violation('GATE_DENIED')
        history = [r for r in self._reviews(tx) if (r.run_id, r.candidate_index) == (data.run_id, data.candidate_index)]
        previous = history[-1] if history else None
        if data.expected_review_revision != (previous.revision if previous else 0):
            raise Violation('CONFLICT')
        if previous and previous.disposition == 'ADMIT':
            raise Violation('GATE_DENIED')
        anchor = m.SourceAnchor(document_id=data.source_id, document_hash=result.source_hash,
            locator=m.Locator(unit='RECORD', value=canonical(dict(ingestion_run=str(data.run_id),
                result_hash=data.result_hash, candidate_index=data.candidate_index,
                fragment=candidate.fragment, start=candidate.start, end=candidate.end)),
                fragment_hash=sha256(candidate.quote.encode()).hexdigest()))
        created = []
        if data.disposition == 'REJECT':
            if data.statement is not None or data.description is not None or data.subjects:
                raise Violation('SCHEMA_INVALID')
        else:
            if not data.description or not data.description.strip():
                raise Violation('SCHEMA_INVALID')
            if candidate.kind == 'FACT' and (not data.statement or not data.statement.strip()):
                raise Violation('SCHEMA_INVALID')
            if candidate.kind == 'EVIDENCE' and (data.statement is not None or data.subjects):
                raise Violation('SCHEMA_INVALID')
            intent = request.model_copy(update={'anchors': (anchor,)})
            metadata = self._metadata(intent, principal, now, 'Evidence')
            metadata['provenance']['tool'] = result.extractor.model_dump(mode='json')
            evidence = entity_from(dict(**metadata, status='REGISTERED', evidence_type='DOCUMENT',
                description=data.description, source=anchor.model_dump(mode='json'), authenticity='UNKNOWN'), m.Evidence)
            self._save(evidence, None, intent, tx, records, heads, principal)
            created.append(ref(evidence))
            if candidate.kind == 'FACT':
                metadata = self._metadata(intent, principal, now, 'Fact')
                metadata['provenance']['tool'] = result.extractor.model_dump(mode='json')
                fact = entity_from(dict(**metadata, status='CANDIDATE', statement=data.statement,
                    support='SOURCE_BACKED', evidence=[ref(evidence).model_dump(mode='json')],
                    subjects=[r.model_dump(mode='json') for r in data.subjects], key_fact=True), m.Fact)
                self._save(fact, None, intent, tx, records, heads, principal)
                created.append(ref(fact))
        receipt = CandidateReviewRecord(id=uuid5(request.meta.command_id, 'candidate-review'),
            tenant_id=principal.tenant_id, case_id=principal.case_id, run_id=data.run_id,
            source_id=data.source_id, result_hash=data.result_hash, candidate_index=data.candidate_index,
            candidate_kind=candidate.kind, revision=(previous.revision + 1 if previous else 1),
            previous_hash=digest(previous) if previous else None, disposition=data.disposition,
            actor=principal.actor, recorded_at=now, rationale=request.rationale, anchor=anchor, created=tuple(created))
        tx.put_object('candidate_review', receipt.id, receipt)
        return tuple(created), 'RevisionAppended', receipt

    def _save(self, entity, old, request, tx, records, heads, principal):
        self._validate(entity, old, tx, records, heads, principal)
        tx.append(entity)
        records[ref(entity)] = entity
        heads[(entity.kind, entity.id)] = entity
        self._dependencies(entity, request, tx, records)

    @staticmethod
    def _dependencies(entity, request, tx, records):
        if entity.kind != 'Fact':
            return
        inputs = (*entity.evidence, *((entity.acceptance,) if entity.acceptance else ()))
        for target in inputs:
            edge = wire.DependencyEdge(source=target, target=ref(entity), input_hash=digest(records[target]))
            tx.put_object('dependency', uuid5(request.meta.command_id, digest(edge)), edge)

    def _evidence_issues(self, evidence, tx, reviews):
        issues = []
        try:
            tx.source_bytes(evidence.source.document_id)
        except (Violation, ValueError, ValidationError):
            issues.extend(('PROVENANCE_UNAVAILABLE', 'ORIGINAL_UNAVAILABLE'))
        for review in reviews:
            try:
                if any(r.kind == 'Evidence' and r.id == evidence.id for r in review.created):
                    self._extraction(tx, review.source_id, review.run_id, review.result_hash)
                    if evidence.source != review.anchor:
                        raise Violation('INVALID_HASH')
            except (Violation, ValueError, ValidationError):
                issues.extend(('PROVENANCE_UNAVAILABLE', 'EXTRACTION_UNAVAILABLE'))
        if evidence.status != 'ACCEPTED':
            issues.append('EVIDENCE_NOT_ACCEPTED')
        if evidence.authenticity == 'DISPUTED':
            issues.append('AUTHENTICITY_DISPUTED')
        return tuple(sorted(set(issues)))

    def _fact_issues(self, fact, tx, records, heads, principal, reviews):
        issues = []
        if fact.support != 'SOURCE_BACKED' or not fact.evidence:
            issues.append('NOT_SOURCE_BACKED')
        for target in fact.evidence:
            current = heads.get(('Evidence', target.id))
            if current is None or ref(current) != target:
                issues.append('STALE_EVIDENCE')
            if current:
                issues.extend(self._evidence_issues(current, tx, reviews))
        for anchor in fact.provenance.anchors:
            try: tx.source_bytes(anchor.document_id)
            except Violation: issues.append('PROVENANCE_UNAVAILABLE')
        return sorted(set(issues))

    def _apply(self, request, principal, tx, records, heads, now):
        operation = request.operation
        if operation == 'ReviewCandidate':
            return self._review_candidate(request, principal, tx, records, heads, now)
        if request.target is None:
            raise Violation('SCHEMA_INVALID')
        kind = 'Evidence' if 'Evidence' in operation else 'Fact'
        old = self._target(request, records, heads, kind)
        data = request.data.model_dump(mode='json', exclude_unset=True)
        reviews = self._reviews(tx)
        if operation == 'ConfirmFact' and self._fact_issues(old, tx, records, heads, principal, reviews):
            raise Violation('GATE_DENIED')
        if operation == 'AcceptEvidence' and 'PROVENANCE_UNAVAILABLE' in self._evidence_issues(old, tx, reviews):
            raise Violation('PROVENANCE_MISSING')
        if operation == 'AcceptEvidence' and old.authenticity == 'DISPUTED':
            raise Violation('GATE_DENIED')
        if operation in ('ReviewFact', 'ConfirmFact', 'DisputeFact', 'UpdateFact'):
            if operation == 'UpdateFact' and old.status == 'REJECTED':
                raise Violation('GATE_DENIED')
            # Reuse the published Core guard, but keep Stage 05's audit operation.
            raw = request.model_dump(mode='json')
            raw.update(contract='urn:lukart:work:CoreRequest:1.0.0',
                operation='EditFact' if operation == 'UpdateFact' else operation, data=data)
            raw.pop('anchors')
            raw.pop('inputs')
            subjects, event, entity = super()._apply(CoreRequest.model_validate_json(json.dumps(raw)), principal, tx, records, heads, now)
            self._dependencies(entity, request, tx, records)
            return subjects, event, entity
        body = old.model_dump(mode='json')
        # Preserve authoritative provenance anchors across lifecycle changes.
        intent = request.model_copy(update={'anchors': old.provenance.anchors, 'inputs': old.provenance.inputs})
        body.update(self._metadata(intent, principal, now, old.kind, old))
        if operation == 'UpdateEvidence':
            if old.status in ('ACCEPTED', 'EXCLUDED'):
                raise Violation('GATE_DENIED')
            body.update(data)
        elif operation in CHANGES:
            body['status'] = CHANGES[operation][1]
            if old.kind == 'Fact': body['acceptance'] = None
        else:
            raise Violation('FORBIDDEN')
        entity = entity_from(body, type(old))
        self._save(entity, old, intent, tx, records, heads, principal)
        return (ref(entity),), 'RevisionAppended', entity

    def matrix(self, raw, token):
        try:
            query = FactEvidenceQuery.model_validate_json(json.dumps(strict_json(raw)))
            with self.authority.session(token) as p:
                p.require(query.tenant_id, query.case_id, query.operation)
                if p.actor.kind == 'AI': raise Violation('FORBIDDEN')
                with self.repository.transaction(p.tenant_id, p.case_id) as tx:
                    if not tx.sequence(): raise Violation('BROKEN_REFERENCE')
                    records = tx.records()
                    heads = {(e.kind, e.id): e for e in tx.heads()}
                    reviews = self._reviews(tx)
                    facts, evidence = [], []
                    for current in sorted(heads.values(), key=lambda e: (e.kind, str(e.id))):
                        if current.kind == 'Evidence':
                            issues = self._evidence_issues(current, tx, reviews)
                            evidence.append(EvidenceAssessment(evidence=ref(current), status=current.status,
                                authenticity=current.authenticity, source_available='ORIGINAL_UNAVAILABLE' not in issues,
                                provenance_available='PROVENANCE_UNAVAILABLE' not in issues, issues=issues))
                        if current.kind != 'Fact': continue
                        issues = self._fact_issues(current, tx, records, heads, p, reviews)
                        live = False
                        if current.acceptance:
                            try:
                                d = self._live_decision(current.acceptance, records, heads, p)
                                live = (d.decision_type == 'FACT_ACCEPTANCE' and d.outcome == 'ACCEPT' and
                                    d.decided_by.kind == 'HUMAN' and current.revision > 1 and
                                    m.Ref(kind='Fact', id=current.id, revision=current.revision - 1) in d.targets)
                            except Violation: pass
                        if not live: issues.append('NO_LIVE_ACCEPTANCE')
                        used = []
                        for consumer in heads.values():
                            if consumer.id == current.id and consumer.kind == 'Fact': continue
                            refs = (r for name in type(consumer).model_fields if name != 'provenance'
                                    for r in walk(getattr(consumer, name), m.Ref))
                            if any(r.kind == 'Fact' and r.id == current.id for r in refs): used.append(ref(consumer))
                        facts.append(FactAssessment(fact=ref(current), statement=current.statement, status=current.status,
                            support=current.support, evidence=current.evidence, acceptance_live=live,
                            confirmation_current=current.status == 'CONFIRMED' and not issues,
                            issues=tuple(sorted(set(issues))), used_in=tuple(sorted(used, key=lambda r: (r.kind, str(r.id), r.revision)))))
                    result = FactEvidenceMatrix(tenant_id=p.tenant_id, case_id=p.case_id, case_sequence=tx.sequence(),
                        facts=tuple(facts), evidence=tuple(evidence), candidate_reviews=reviews)
                    p.require(query.tenant_id, query.case_id, query.operation)
                    return result
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (ValidationError, ValueError, TypeError, KeyError, RecursionError):
            return safe_error('SCHEMA_INVALID', UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith('psycopg'):
                return safe_error('UNKNOWN', UUID(int=0))
            raise
