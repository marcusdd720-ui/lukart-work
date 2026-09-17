"""Fail-closed Document Registry over authoritative Core/Filing history."""
from hashlib import sha256
import json
from uuid import UUID, uuid5
from pydantic import ValidationError

from lukart_work.contracts import messages as wire
from lukart_work.core.postgres import canonical
from lukart_work.core.requests import CoreRequest
from lukart_work.core.service import CommandService, entity_from, safe_error
from lukart_work.domain import models as m
from lukart_work.validation.rules import Violation, digest, ref, strict_json
from .contracts import FilingRegistryEntry, RegistryProjection, RegistryQuery, RegistryReceipt, RegistryRequest

CATEGORY='filing_registry_receipt'
IMPLEMENTATION=m.VersionPin(id='urn:lukart:work:DocumentRegistryService',version='1.0.0',
    content_hash=sha256(b'lukart-work:document-registry:1.0.0').hexdigest())
STATUS_EVENT={'PLANNED':'REGISTERED','PREPARING':'PREPARED','READY':'READY','SUBMITTED':'SUBMITTED','ACKNOWLEDGED':'ACKNOWLEDGED','WITHDRAWN':'WITHDRAWN'}
OP_STATUS={'PrepareFiling':'PREPARING','MarkFilingReady':'READY','RecordSubmission':'SUBMITTED','RecordAcknowledgement':'ACKNOWLEDGED','WithdrawFiling':'WITHDRAWN'}

class DocumentRegistryService(CommandService):
    def _parse_request(self,raw):
        value=strict_json(raw); stack=[(value,0)]
        while stack:
            item,depth=stack.pop()
            if depth>64: raise Violation('SCHEMA_INVALID')
            if isinstance(item,dict): stack.extend((v,depth+1) for v in item.values())
            elif isinstance(item,list): stack.extend((v,depth+1) for v in item)
        return RegistryRequest.model_validate_json(json.dumps(value,allow_nan=False))

    def _case_guard(self,request,principal,case):
        super()._case_guard(request,principal,case)
        if principal.actor.kind!='HUMAN': raise Violation('FORBIDDEN')

    @staticmethod
    def _request_hash(request,principal):
        return digest({'request':request.model_dump(mode='json'),'actor':principal.actor.model_dump(mode='json')})

    @staticmethod
    def _source(tx,source_id):
        source=tx.object('source',source_id,wire.SourceDocument); data=tx.source_bytes(source_id)
        if len(data)!=source.byte_length or sha256(data).hexdigest()!=source.content_hash: raise Violation('INVALID_HASH')
        return source

    @classmethod
    def _anchor(cls,tx,source_id,purpose):
        source=cls._source(tx,source_id)
        locator=m.Locator(unit='RECORD',value=canonical({'purpose':purpose,'source_id':str(source_id)}),fragment_hash=source.content_hash)
        return source,m.SourceAnchor(document_id=source.id,document_hash=source.content_hash,locator=locator)

    @staticmethod
    def _history(tx):
        values=sorted(tx.objects(CATEGORY,RegistryReceipt),key=lambda r:(str(r.filing.id),r.sequence))
        records=tx.records(); groups={}
        for receipt in values: groups.setdefault(receipt.filing.id,[]).append(receipt)
        for history in groups.values():
            first=history[0]
            if first.sequence!=1 or first.event!='REGISTERED' or first.filing.revision!=1: raise Violation('INVALID_HASH')
            identity=(first.artifact_source_id,first.artifact_hash,first.artifact_byte_length); previous=None
            for index,receipt in enumerate(history,1):
                if receipt.sequence!=index or receipt.filing.revision!=index: raise Violation('INVALID_HASH')
                if receipt.previous_hash!=(digest(previous) if previous else None): raise Violation('INVALID_HASH')
                if (receipt.artifact_source_id,receipt.artifact_hash,receipt.artifact_byte_length)!=identity: raise Violation('INVALID_HASH')
                if receipt.evidence is not None:
                    evidence=records.get(receipt.evidence)
                    if evidence is None or evidence.kind!='Evidence' or evidence.status!='ACCEPTED' or evidence.authenticity=='DISPUTED': raise Violation('INVALID_HASH')
                    if evidence.source!=receipt.evidence_anchor: raise Violation('INVALID_HASH')
                previous=receipt
        return tuple(values)

    @classmethod
    def _filing_history(cls,tx,filing_id): return tuple(r for r in cls._history(tx) if r.filing.id==filing_id)

    @classmethod
    def _registered_identity(cls,tx,filing_id):
        history=cls._filing_history(tx,filing_id)
        if not history: raise Violation('GATE_DENIED')
        first=history[0]; source=cls._source(tx,first.artifact_source_id)
        if (source.content_hash,source.byte_length)!=(first.artifact_hash,first.artifact_byte_length): raise Violation('INVALID_HASH')
        return history,source

    @classmethod
    def _ensure_unique_receipt_evidence(cls,tx,source,artifact):
        if source.id==artifact.id or source.content_hash==artifact.content_hash: raise Violation('GATE_DENIED')
        for existing in cls._history(tx):
            anchor=existing.evidence_anchor
            if anchor is not None and (anchor.document_id==source.id or anchor.document_hash==source.content_hash): raise Violation('GATE_DENIED')

    @staticmethod
    def _accepted_evidence(records,heads,evidence_ref,source):
        current=heads.get(('Evidence',evidence_ref.id))
        if current is None: raise Violation('BROKEN_REFERENCE')
        if ref(current)!=evidence_ref: raise Violation('STALE')
        if current.status!='ACCEPTED' or current.authenticity=='DISPUTED': raise Violation('GATE_DENIED')
        if current.source.document_id!=source.id or current.source.document_hash!=source.content_hash: raise Violation('GATE_DENIED')
        if records.get(evidence_ref)!=current: raise Violation('INVALID_HASH')
        return current

    def _append_receipt(self,request,principal,tx,filing,artifact,now,*,evidence_anchor=None,evidence=None):
        history=self._filing_history(tx,filing.id); previous=history[-1] if history else None; event=STATUS_EVENT[filing.status]
        receipt_class='SUBMISSION' if event=='SUBMITTED' else 'ACKNOWLEDGEMENT' if event=='ACKNOWLEDGED' else 'REGISTRY'
        receipt=RegistryReceipt(id=uuid5(request.meta.command_id,'filing-registry-receipt'),tenant_id=principal.tenant_id,case_id=principal.case_id,
            filing=ref(filing),sequence=previous.sequence+1 if previous else 1,previous_hash=digest(previous) if previous else None,event=event,
            receipt_class=receipt_class,actor=principal.actor,recorded_at=now,operation=request.operation,input_hash=self._request_hash(request,principal),
            implementation=IMPLEMENTATION,artifact_source_id=artifact.id,artifact_hash=artifact.content_hash,artifact_byte_length=artifact.byte_length,
            evidence_anchor=evidence_anchor,evidence=evidence)
        if receipt.sequence!=filing.revision: raise Violation('INVALID_HASH')
        tx.put_object(CATEGORY,receipt.id,receipt); return receipt

    def _register(self,request,principal,tx,records,heads,now):
        data=request.data; artifact,artifact_anchor=self._anchor(tx,data.source_id,'FILING_ARTIFACT')
        core=CoreRequest(contract='urn:lukart:work:CoreRequest:1.0.0',operation='AddFiling',meta=request.meta,
            data={'document_type':data.document_type.model_dump(mode='json'),'direction':data.direction,
                  'proceeding':data.proceeding.model_dump(mode='json') if data.proceeding else None,
                  'recipient':data.recipient.model_dump(mode='json'),'authors':[r.model_dump(mode='json') for r in data.authors]},
            anchors=(artifact_anchor,),rationale=request.rationale)
        _,_,filing=super()._apply(core,principal,tx,records,heads,now); records[ref(filing)]=filing; heads[(filing.kind,filing.id)]=filing
        receipt=self._append_receipt(request,principal,tx,filing,artifact,now); return (ref(filing),),'RevisionAppended',receipt

    def _transition(self,request,principal,tx,records,heads,now):
        old=self._target(request,records,heads,'Filing'); _,artifact=self._registered_identity(tx,old.id); target_status=OP_STATUS[request.operation]
        body=old.model_dump(mode='json'); body.update(self._metadata(request,principal,now,old.kind,old)); body['status']=target_status
        evidence_anchor=evidence_ref=None
        if request.operation=='RecordSubmission':
            receipt_source,_=self._anchor(tx,request.data.receipt_source_id,'SUBMISSION_RECEIPT')
            self._ensure_unique_receipt_evidence(tx,receipt_source,artifact)
            accepted=self._accepted_evidence(records,heads,request.data.evidence,receipt_source)
            evidence_ref=ref(accepted); evidence_anchor=accepted.source
            body['submitted_at']=now.isoformat(); body['submission_receipt']=evidence_anchor.model_dump(mode='json')
        elif request.operation=='RecordAcknowledgement':
            if old.submission_receipt is None or old.submitted_at is None: raise Violation('GATE_DENIED')
            submission_source=self._source(tx,old.submission_receipt.document_id)
            receipt_source,_=self._anchor(tx,request.data.receipt_source_id,'ACKNOWLEDGEMENT_RECEIPT')
            self._ensure_unique_receipt_evidence(tx,receipt_source,artifact)
            if receipt_source.content_hash==submission_source.content_hash: raise Violation('GATE_DENIED')
            accepted=self._accepted_evidence(records,heads,request.data.evidence,receipt_source)
            evidence_ref=ref(accepted); evidence_anchor=accepted.source
        elif request.operation in ('PrepareFiling','MarkFilingReady','WithdrawFiling'):
            if request.data.model_fields_set: raise Violation('SCHEMA_INVALID')
        else: raise Violation('FORBIDDEN')
        entity=entity_from(body,m.Filing); self._validate(entity,old,tx,records,heads,principal); tx.append(entity)
        records[ref(entity)]=entity; heads[(entity.kind,entity.id)]=entity
        receipt=self._append_receipt(request,principal,tx,entity,artifact,now,evidence_anchor=evidence_anchor,evidence=evidence_ref)
        return (ref(entity),),'RevisionAppended',receipt

    def _apply(self,request,principal,tx,records,heads,now):
        return self._register(request,principal,tx,records,heads,now) if request.operation=='RegisterFiling' else self._transition(request,principal,tx,records,heads,now)

    def registry(self,raw,token):
        try:
            query=RegistryQuery.model_validate_json(json.dumps(strict_json(raw)))
            with self.authority.session(token) as principal:
                principal.require(query.tenant_id,query.case_id,query.operation)
                if principal.actor.kind=='AI': raise Violation('FORBIDDEN')
                with self.repository.transaction(query.tenant_id,query.case_id) as tx:
                    sequence=tx.sequence()
                    if not sequence: raise Violation('BROKEN_REFERENCE')
                    heads=tuple(tx.heads()); receipts=self._history(tx); by_filing={}
                    for receipt in receipts: by_filing.setdefault(receipt.filing.id,[]).append(receipt)
                    entries=[]; unregistered=[]
                    for current in sorted((e for e in heads if e.kind=='Filing'),key=lambda e:str(e.id)):
                        if query.filing_id is not None and current.id!=query.filing_id: continue
                        history=tuple(by_filing.get(current.id,()))
                        if not history: unregistered.append(ref(current)); continue
                        artifact=self._source(tx,history[0].artifact_source_id)
                        if (artifact.content_hash,artifact.byte_length)!=(history[0].artifact_hash,history[0].artifact_byte_length): raise Violation('INVALID_HASH')
                        if history[-1].filing!=ref(current): raise Violation('STALE')
                        if history[-1].event!=STATUS_EVENT[current.status]: raise Violation('INVALID_HASH')
                        submission_record=next((r for r in reversed(history) if r.event=='SUBMITTED'),None)
                        acknowledgement_record=next((r for r in reversed(history) if r.event=='ACKNOWLEDGED'),None)
                        if submission_record: self._source(tx,submission_record.evidence_anchor.document_id)
                        if acknowledgement_record: self._source(tx,acknowledgement_record.evidence_anchor.document_id)
                        entries.append(FilingRegistryEntry(filing=ref(current),direction=current.direction,status=current.status,document_type=current.document_type,
                            proceeding=current.proceeding,recipient=current.recipient,authors=current.authors,artifact_source_id=artifact.id,
                            artifact_hash=artifact.content_hash,artifact_byte_length=artifact.byte_length,submitted_at=current.submitted_at,
                            submission_receipt=submission_record.evidence_anchor if submission_record else None,
                            submission_evidence=submission_record.evidence if submission_record else None,
                            acknowledgement_receipt=acknowledgement_record.evidence_anchor if acknowledgement_record else None,
                            acknowledgement_evidence=acknowledgement_record.evidence if acknowledgement_record else None,receipt_count=len(history)))
                    result=RegistryProjection(tenant_id=query.tenant_id,case_id=query.case_id,case_sequence=sequence,filings=tuple(entries),
                        history=tuple(r for r in receipts if query.filing_id is None or r.filing.id==query.filing_id),unregistered_filings=tuple(unregistered))
                    principal.require(query.tenant_id,query.case_id,query.operation); return result
        except Violation as error: return safe_error(error.code,UUID(int=0))
        except (ValidationError,ValueError,TypeError,KeyError,RecursionError): return safe_error('SCHEMA_INVALID',UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith('psycopg'): return safe_error('UNKNOWN',UUID(int=0))
            raise
