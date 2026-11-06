from pathlib import Path
import re
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]


class BatchWorkflowTests(unittest.TestCase):
    def workflow(self):
        path=ROOT/'.github/workflows/ap-mail-batch.yml'
        self.assertTrue(path.exists(),'guarded twice-daily workflow is missing')
        raw=path.read_text()
        return yaml.load(raw,Loader=yaml.BaseLoader),raw

    def test_schedule_is_guarded_free_and_manual_ref_is_not_an_input(self):
        workflow,raw=self.workflow()
        self.assertEqual(set(workflow['on']),{'schedule','workflow_dispatch'})
        self.assertEqual(workflow['on']['schedule'],[{'cron':'17 8,16 * * *','timezone':'America/New_York'}])
        self.assertFalse(workflow['on']['workflow_dispatch'])
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertEqual(workflow['concurrency'],{'group':'ap-mail-free-batch','cancel-in-progress':'false'})
        self.assertEqual(set(workflow['jobs']),{'intake'})
        job=workflow['jobs']['intake']
        self.assertEqual(job['runs-on'],'ubuntu-24.04');self.assertEqual(job['timeout-minutes'],'20')
        for clause in ["vars.AP_MAIL_BATCH_ENABLED == 'true'","github.repository == 'kcurrycruz/daily-deposit-automation'",
                       'github.event.repository.private == false',"github.ref == 'refs/heads/main'",
                       "github.event.repository.default_branch == 'main'"]:
            self.assertIn(clause,job['if'])
        self.assertNotIn('||',job['if']);self.assertNotIn('pull_request',raw)
        for forbidden in ['actions/cache','actions/upload-artifact','id-token: write','--no-sandbox','docker build','gcloud ','terraform apply']:
            self.assertNotIn(forbidden,raw)

    def test_checkout_and_actions_are_immutable_and_install_cannot_see_credentials(self):
        workflow,raw=self.workflow();steps=workflow['jobs']['intake']['steps']
        for step in steps:
            if 'uses' in step:self.assertRegex(step['uses'],r'^actions/(checkout|setup-python|setup-node)@[a-f0-9]{40}$')
        checkout=next(x for x in steps if x.get('uses','').startswith('actions/checkout@'))
        self.assertRegex(checkout['with']['ref'],r'^[a-f0-9]{40}$')
        self.assertEqual(checkout['with']['persist-credentials'],'false')
        self.assertEqual(checkout['with']['ref'],workflow['env']['AP_MAIL_SOURCE_SHA'])
        python=next(x for x in steps if x.get('uses','').startswith('actions/setup-python@'))
        node=next(x for x in steps if x.get('uses','').startswith('actions/setup-node@'))
        self.assertEqual(python['with']['python-version'],'3.12');self.assertNotIn('cache',python['with'])
        self.assertEqual(node['with']['node-version'],'24');self.assertEqual(node['with']['package-manager-cache'],'false')
        processing=next(x for x in steps if x.get('run')=='python -m workers.ap_mail.batch')
        self.assertEqual(processing['env']['AP_MAIL_GMAIL_GRANT'],'${{ secrets.AP_MAIL_GMAIL_GRANT }}')
        self.assertEqual(processing['env']['AP_MAIL_SUPABASE_KEY'],'${{ secrets.AP_MAIL_SUPABASE_KEY }}')
        for step in steps:
            if step is not processing:self.assertNotIn('secrets.',str(step))
        self.assertNotIn('secrets.',str(workflow['env']))
        self.assertNotIn('secrets.',str({k:v for k,v in workflow['jobs']['intake'].items() if k!='steps'}))

    def test_matching_browser_smoke_precedes_secret_bearing_processing(self):
        workflow,raw=self.workflow();steps=workflow['jobs']['intake']['steps']
        processing=next(i for i,x in enumerate(steps) if x.get('run')=='python -m workers.ap_mail.batch')
        smoke=next(i for i,x in enumerate(steps) if x.get('run')=='python -m workers.ap_mail.smoke')
        self.assertLess(smoke,processing)
        installs='\n'.join(x.get('run','') for x in steps[:smoke])
        for command in ['--require-hashes -r workers/ap_mail/requirements.lock','npm ci --prefix app/ap_statements',
                        'npm ci --prefix workers/ap_mail','node app/ap_statements/build.mjs',
                        'node workers/ap_mail/node_modules/playwright/cli.js install --with-deps chromium']:
            self.assertIn(command,installs)
        self.assertNotIn('set -x',raw);self.assertNotIn('printenv',raw)
        self.assertEqual(workflow['env']['AP_MAIL_RUNNER'],'ubuntu-24.04')
