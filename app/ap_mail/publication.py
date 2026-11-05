"""Assess complete candidate inventories and publish through one fenced transaction."""
from dataclasses import asdict
from uuid import UUID,uuid5
from .contracts import MailError,canonical,payload_digest


class MailPublication:
    def __init__(self,repository,domain,authorize=lambda claim:True):self.repo,self.domain,self.authorize=repository,domain,authorize

    def assess(self,extracted,claim,pin):
        if self.authorize(claim) is False:raise MailError('stale_claim')
        byte=self.repo.byte_match(claim.receipt_id)
        if byte:return dict(kind='duplicate',match=byte,repeated=0,added=0,byte_identical=True)
        mappings=None
        def page(cursor):
            nonlocal mappings
            if self.authorize(claim) is False:raise MailError('stale_claim')
            result=self.repo.candidates_page(cursor,50)
            if result['epoch']!=pin.protection_epoch or result['mappingVersions']!=pin.mapping_versions:raise MailError('stale_source')
            if mappings is None:mappings=result['mappings']
            if result['mappings']!=mappings or payload_digest({'mappings':mappings,'versions':result['mappingVersions']})!=pin.mapping_digest:raise MailError('stale_source')
            return result
        first=page(None)
        def read(action,payload):
            if action!='statement_candidates_page' or set(payload)!=set(('cursor',)):raise MailError('denied')
            return page(payload['cursor'])
        result=self.domain.run('assess',dict(doc=extracted,stream=True,firstPage=first),read=read,heartbeat=lambda:self.authorize(claim))
        match=result.get('match')
        if match:result['match']={key:match[key] for key in ('id','revision_id','version')}
        return result

    def publish(self,extracted,assessment,evidence,claim,pin):
        if extracted.get('confirmed') is not False or evidence.get('preliminary') is not True:raise MailError('invalid')
        payload=dict(doc=extracted,assessment=assessment,evidence=evidence,claim=asdict(claim),pin=asdict(pin))
        request=str(uuid5(UUID(claim.job_id),'publish:'+payload_digest(payload)))
        return self.repo.publish(payload,request)
