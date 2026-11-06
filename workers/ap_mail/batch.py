"""Finite GitHub-hosted intake. SQL owns recovery; no cloud queue or HTTP server."""
from dataclasses import dataclass
from datetime import datetime,timezone
import json
import logging
import os
from pathlib import Path
import re
import time

from app.ap_mail.contracts import CODES,MailConfig,MailError,identifier,natural
from app.ap_mail.sync import MailSync
from .github import REPOSITORY,EnvironmentGrantStore,grant_reference
from .shared import BoundedTransport,DeferredGmail,GmailTokens,build_processor

WORKFLOW=REPOSITORY+'/.github/workflows/ap-mail-batch.yml@refs/heads/main'
RUNNER='ubuntu-24.04'
RESULTS=('awaiting_review','already_imported','needs_attention','retry','not_claimed','skipped')


@dataclass(frozen=True)
class BatchConfig:
    mail: MailConfig
    repository: str=REPOSITORY
    grant_ref: str=grant_reference(REPOSITORY)
    budget_seconds: int=840
    max_jobs: int=10


def validate_context(env,event):
    try:
        if env.get('AP_MAIL_BATCH_ENABLED')!='true':
            raise MailError('paused')
        repository=event.get('repository',{})
        if (env.get('GITHUB_REPOSITORY')!=REPOSITORY or repository.get('full_name')!=REPOSITORY or
            repository.get('private') is not False or repository.get('default_branch')!='main' or
            env.get('GITHUB_REF')!='refs/heads/main' or env.get('GITHUB_WORKFLOW_REF')!=WORKFLOW or
            env.get('GITHUB_EVENT_NAME') not in ('schedule','workflow_dispatch') or
            env.get('RUNNER_ENVIRONMENT')!='github-hosted' or env.get('RUNNER_OS')!='Linux' or
            env.get('RUNNER_ARCH')!='X64' or env.get('AP_MAIL_RUNNER')!=RUNNER):
            raise MailError('denied')
        if not re.fullmatch('[0-9a-f]{40}',env.get('AP_MAIL_SOURCE_SHA','')):
            raise MailError('invalid')
        if env.get('GITHUB_EVENT_NAME')=='schedule' and env.get('AP_MAIL_SCHEDULE_ENABLED')!='true':
            raise MailError('paused')
        reference=grant_reference(REPOSITORY)
        EnvironmentGrantStore(reference,env.get('AP_MAIL_GMAIL_GRANT','')).read(reference)
        mail=MailConfig(env['AP_MAIL_SUPABASE_URL'],env['AP_MAIL_SUPABASE_KEY'],
            env['AP_MAIL_WORKSPACE_ID'],env['AP_MAIL_BUCKET'],env['AP_MAIL_CONNECTION_ID'],'processor')
        return BatchConfig(mail)
    except MailError:
        raise
    except Exception:
        raise MailError('invalid') from None


def load_context():
    try:
        path=Path(os.environ['GITHUB_EVENT_PATH'])
        if path.stat().st_size>131072:
            raise MailError('limit')
        raw=path.read_bytes()
        if len(raw)>131072:
            raise MailError('limit')
        return validate_context(os.environ,json.loads(raw))
    except MailError:
        raise
    except Exception:
        raise MailError('invalid') from None


def _connection(repository,expected=None):
    home=repository.connection()
    if not home:
        raise MailError('not_configured')
    if (home.get('id')!=repository.config.connection_id or home.get('workspace_id')!=repository.config.workspace_id or
        home.get('secret_ref')!=grant_reference(REPOSITORY)):
        raise MailError('denied')
    natural(home['generation'],1)
    if type(home.get('active')) is not bool or type(home.get('paused')) is not bool:
        raise MailError('invalid')
    binding=tuple(home.get(key) for key in ('id','generation','account_id','email','label_id','secret_ref'))
    if expected is not None and binding!=expected:
        raise MailError('wrong_account')
    return home,binding


class BatchRunner:
    def __init__(self,repository,gmail_factory,process,*,clock=time.monotonic):
        self.repo,self.clock,self.process=repository,clock,process
        self.sync=MailSync(DeferredGmail(gmail_factory),repository,lambda:datetime.now(timezone.utc),clock)

    def run(self,*,budget_seconds=840,max_jobs=10):
        natural(budget_seconds,1,840);natural(max_jobs,1,10)
        deadline=self.clock()+budget_seconds
        result=dict(status='ok',discovery_status='not_checked',discovered=0,queued=0,
                    attempted=0,next_work=False,**{key:0 for key in RESULTS})
        try:
            home,binding=_connection(self.repo)
            # Recovery can clear an expired Scanning entry even while new work is paused.
            self.repo.mutate('reconcile',{'limit':100})
            home,_=_connection(self.repo,binding)
            if not home['active'] or home['paused']:
                result['status']='paused';return result
            try:
                remaining=max(1,min(20,int(deadline-self.clock())))
                polled=self.sync.poll(home['id'],budget_seconds=remaining,queue_stale=False)
                if polled.status not in CODES|{'ok'}:
                    raise MailError('unavailable')
                result.update(discovery_status=polled.status,
                              discovered=natural(polled.discovered,0,1000000),
                              queued=natural(polled.queued,0,1000000),next_work=bool(polled.next_work))
                if polled.status!='ok':
                    result.update(status='partial',reason=polled.status)
            except Exception as error:
                code=error.code if isinstance(error,MailError) else 'unavailable'
                result.update(status='partial',discovery_status=code,reason=code,next_work=True)
                try:
                    self.repo.mutate('sync_error',dict(connection_id=home['id'],expected_generation=home['generation'],reason=code))
                except MailError:
                    pass
            home,_=_connection(self.repo,binding)
            if not home['active'] or home['paused']:
                result.update(status='paused',next_work=True);return result
            self.repo.queue_stale(50)
            cursor=None;seen=set()
            for _ in range(10):
                if result['attempted']>=max_jobs or deadline-self.clock()<600:
                    result['next_work']=True;break
                home,_=_connection(self.repo,binding)
                if not home['active'] or home['paused']:
                    result.update(status='paused',next_work=True);break
                page=self.repo.batch_pending(home['generation'],cursor,25)
                if type(page) is not dict or type(page.get('items')) is not list or len(page['items'])>25:
                    raise MailError('unavailable')
                stopped=False
                for row in page['items']:
                    if result['attempted']>=max_jobs or deadline-self.clock()<600:
                        result['next_work']=True;stopped=True;break
                    current,_=_connection(self.repo,binding)
                    if not current['active'] or current['paused']:
                        result.update(status='paused',next_work=True);stopped=True;break
                    if type(row) is not dict or set(row)!=set(('job_id','receipt_id','dispatch_generation','mode')):
                        raise MailError('unavailable')
                    identifier(row['job_id']);identifier(row['receipt_id']);natural(row['dispatch_generation'],1)
                    if row['mode'] not in ('extract','recompare'):
                        raise MailError('invalid')
                    identity=(row['job_id'],row['dispatch_generation'])
                    if identity in seen:
                        continue
                    seen.add(identity);result['attempted']+=1
                    try:
                        reply=self.process(row['job_id'],row['dispatch_generation'])
                        status=reply.get('status')
                        if status not in RESULTS:
                            raise MailError('unavailable')
                        result[status]+=1
                        if status in ('retry','not_claimed'):
                            result['next_work']=True
                    except Exception as error:
                        result.update(status='partial',reason=error.code if isinstance(error,MailError) else 'unavailable',next_work=True)
                if stopped:
                    break
                next_cursor=page.get('nextCursor')
                if next_cursor is None:
                    break
                identifier(next_cursor)
                if cursor is not None and next_cursor<=cursor:
                    raise MailError('unavailable')
                cursor=next_cursor
            else:
                result['next_work']=True
        except Exception as error:
            result.update(status='partial',reason=error.code if isinstance(error,MailError) else 'unavailable',next_work=True)
        return result


def create_runner(config,env):
    from supabase import create_client
    from supabase.client import ClientOptions
    from app.ap_mail.repository import MailRepository
    from app.ap_mail.gmail import GmailClient
    client=create_client(config.mail.supabase_url,config.mail.supabase_secret_key,
        ClientOptions(auto_refresh_token=False,persist_session=False,postgrest_client_timeout=10,storage_client_timeout=10))
    repository=MailRepository(config.mail,client)
    home,binding=_connection(repository)
    secret=EnvironmentGrantStore(config.grant_ref,env['AP_MAIL_GMAIL_GRANT']).read(config.grant_ref)
    tokens=GmailTokens(secret,home)
    def gmail():
        current,_=_connection(repository,binding)
        return GmailClient(BoundedTransport(),tokens,current['account_id'],current['email'],current['label_id'])
    processor,caches=build_processor(repository,gmail)
    return BatchRunner(repository,gmail,processor.run),caches


def main():
    logging.disable(logging.CRITICAL)
    caches=None
    try:
        config=load_context()
        runner,caches=create_runner(config,os.environ)
        result=runner.run(budget_seconds=config.budget_seconds,max_jobs=config.max_jobs)
        print(json.dumps(result,sort_keys=True),flush=True)
        return 0 if result['status'] in ('ok','paused') else 1
    except Exception as error:
        code=error.code if isinstance(error,MailError) else 'unavailable'
        print(json.dumps({'status':'error','reason':code}),flush=True)
        return 1
    finally:
        if caches is not None:
            try:caches.close()
            except Exception:pass


if __name__=='__main__':
    raise SystemExit(main())
