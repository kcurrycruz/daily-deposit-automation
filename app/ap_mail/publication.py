"""Assess complete candidate inventories and publish through one fenced transaction."""
from dataclasses import asdict
from uuid import UUID,uuid5
from .contracts import MailError,canonical,payload_digest


class MailPublication:
    def __init__(self,repository,domain,authorize=lambda claim:True):self.repo,self.domain,self.authorize=repository,domain,authorize

    def assess(self,extracted,claim,pin):
        candidates=[];cursor=None;seen=set();mappings=None
        while True:
            if self.authorize(claim) is False:raise MailError('stale_claim')
            page=self.repo.candidates_page(cursor,50)
            if page['epoch']!=pin.protection_epoch or page['mappingVersions']!=pin.mapping_versions:raise MailError('stale_source')
            if mappings is None:mappings=page['mappings']
            if page['mappings']!=mappings:raise MailError('stale_source')
            candidates.extend(page['items'])
            if len(canonical({'doc':extracted,'candidates':candidates,'mappings':mappings}).encode())>900000:raise MailError('limit')
            cursor=page['nextCursor']
            if cursor is None:break
            if cursor in seen:raise MailError('unavailable')
            seen.add(cursor)
        if payload_digest({'mappings':mappings,'versions':page['mappingVersions']})!=pin.mapping_digest:raise MailError('stale_source')
        result=self.domain.run('assess',dict(doc=extracted,candidates=candidates,mappings=mappings),heartbeat=lambda:self.authorize(claim))
        match=result.get('match')
        if match:result['match']={key:match[key] for key in ('id','revision_id','version')}
        return result

    def publish(self,extracted,assessment,evidence,claim,pin):
        if extracted.get('confirmed') is not False or evidence.get('preliminary') is not True:raise MailError('invalid')
        payload=dict(doc=extracted,assessment=assessment,evidence=evidence,claim=asdict(claim),pin=asdict(pin))
        request=str(uuid5(UUID(claim.job_id),'publish:'+payload_digest(payload)))
        return self.repo.publish(payload,request)
