"""Behavior tests for private knowledge, provenance, revisions and durable imports."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

MODULE=Path(__file__).resolve().parents[1]/'services'/'ai-database'/'ai_database.py'
spec=importlib.util.spec_from_file_location('ai_database',MODULE)
ai=importlib.util.module_from_spec(spec);spec.loader.exec_module(ai)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.path=self.root/'private'/'ai.sqlite3';self.db=ai.Database(self.path,create=True)
        self.source={'id':'src','title':'Owner build note','locator':'Curated test note','basis':'user_statement','observed_at':'2026-10-04T00:00:00Z'}
        self.db.source(self.source)
        self.record={'id':'rule','kind':'knowledge','title':'Frosted laser mirror rule','body':'Diffuse the mirror etch for HUB75 lighting.','metadata':{'leds':72},'source_id':'src','confidence':'user_reported','status':'active'}

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def workflow(self):
        folder=self.root/'checkout'/'docs'/'ai-workflow';folder.mkdir(parents=True)
        state={'schema_version':1,'observed_at':'2026-10-04T00:00:00Z','repository':{'full_name':'Crosby121/MirroriedLED-Public'},'deployment':{'live_commit':None}}
        queue={'schema_version':1,'updated_at':'2026-10-04T01:00:00Z','tasks':[{'id':'WF-001','title':'Connect workflow','status':'blocked','owner_session_id':None,'next_action':'Activate connector','depends_on':[]}]}
        (folder/'state.json').write_text(json.dumps(state));(folder/'tasks.json').write_text(json.dumps(queue))
        return folder,state,queue

    def test_search_carries_provenance_and_quotes_are_safe(self):
        self.db.put(self.record)
        for query in ('HUB75','laser','"HUB75" OR *','HUB75; DROP TABLE records;'):
            results=self.db.search(query);self.assertEqual(results[0]['id'],'rule')
            self.assertEqual(results[0]['source']['observed_at'],self.source['observed_at'])
        self.assertEqual(self.db.search(''),[self.db.get('rule')])

    def test_revision_requires_current_version_and_keeps_both_values(self):
        self.db.put(self.record)
        updated=dict(self.record,body='Revised diffusion rule')
        with self.assertRaises(ValueError):self.db.put(updated)
        self.db.put(updated,expected_version=1)
        with self.assertRaises(ValueError):self.db.put(self.record,expected_version=1)
        self.assertEqual([r['body'] for r in self.db.history('rule')],[self.record['body'],updated['body']])
        self.assertEqual(self.db.search('Revised')[0]['version'],2)

    def test_two_concurrent_edits_cannot_overwrite_each_other(self):
        self.db.put(self.record)
        def edit(body):
            db=ai.Database(self.path)
            try:
                try:db.put(dict(self.record,body=body),expected_version=1);return 'saved'
                except ValueError:return 'conflict'
            finally:db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(edit,['Version A','Version B']))
        self.assertEqual(sorted(results),['conflict','saved'])
        self.assertEqual(len(self.db.history('rule')),2)

    def test_archived_records_excluded_but_retained(self):
        self.db.put(self.record);self.db.put(dict(self.record,status='archived'),1)
        self.assertEqual(self.db.search('laser'),[])
        self.assertEqual(len(self.db.search('laser',include_archived=True)),1)
        self.assertEqual(self.db.get('rule')['status'],'archived')

    def test_unknown_source_and_unknown_fields_refused(self):
        with self.assertRaises(ValueError):self.db.put(dict(self.record,source_id='missing'))
        with self.assertRaises(ValueError):self.db.put(dict(self.record,extra=True))
        self.assertEqual(self.db.status()['record_counts'],{})

    def test_provenance_is_immutable(self):
        self.assertTrue(self.db.source(self.source)['replayed'])
        with self.assertRaises(ValueError):self.db.source(dict(self.source,locator='Different source'))

    def test_bundle_replay_is_idempotent_and_conflict_is_explicit(self):
        bundle={'sources':[self.source],'records':[self.record]}
        self.assertEqual(self.db.bundle(bundle),{'added':1,'replayed':0})
        self.assertEqual(self.db.bundle(bundle),{'added':0,'replayed':1})
        with self.assertRaises(ValueError):self.db.bundle({'sources':[],'records':[dict(self.record,body='Overwritten')]})
        self.assertEqual(len(self.db.history('rule')),1)

    def test_bad_bundle_rolls_back_all_sources_and_records(self):
        with self.assertRaises(ValueError):self.db.bundle({'sources':[dict(self.source,id='new')],'records':[self.record,dict(self.record,id='bad',source_id='missing')]})
        self.assertEqual(self.db.status()['record_counts'],{})
        self.assertEqual(self.db.status()['sources'],1)

    def test_price_requires_basis_and_date_and_missing_cost_stays_null(self):
        product=dict(self.record,id='product',kind='product',metadata={'cost_usd':None,'price_basis':'quote_pending','cost_as_of':'2026-10-04'})
        self.db.put(product);self.assertIsNone(self.db.get('product')['metadata']['cost_usd'])
        for metadata in ({'cost_usd':30},{'cost_usd':-1,'price_basis':'owner_cost','cost_as_of':'2026-10-04'},{'cost_usd':True,'price_basis':'owner_cost','cost_as_of':'2026-10-04'}):
            with self.assertRaises(ValueError):self.db.put(dict(product,id='invalid',metadata=metadata))

    def test_credentials_and_signed_urls_refused(self):
        for body in ('github_pat_'+'X'*50,'-----BEGIN PRIVATE KEY-----','Bearer '+'X'*25,'https://example.com/record?signature=private'):
            with self.assertRaises(ValueError):self.db.put(dict(self.record,body=body))
        with self.assertRaises(ValueError):self.db.put(dict(self.record,metadata={'api_key':'example'}))
        self.assertEqual(self.db.status()['record_counts'],{})

    def test_activity_retries_and_unknown_attribution(self):
        event={'request_id':'req1','action':'import','summary':'Imported known work','source_id':'src'}
        result=self.db.event(event);self.assertEqual(result['application_identity'],'unknown');self.assertIsNone(result['occurred_at'])
        self.assertTrue(self.db.event(event)['replayed'])
        with self.assertRaises(ValueError):self.db.event(dict(event,summary='Changed'))
        self.assertEqual(len(self.db.events()),1)

    def test_declared_app_is_separate_from_authentication(self):
        result=self.db.event({'request_id':'req1','application':'Copilot','action':'handoff','summary':'Saved source','source_id':'src'})
        self.assertEqual(result['application_identity'],'declared')
        self.assertNotIn('authenticated',result)

    def test_workflow_import_preserves_unknown_live_state_and_leaves_source_intact(self):
        folder,state,queue=self.workflow();before=(folder/'tasks.json').read_bytes()
        result=self.db.import_workflow(self.root/'checkout','Exact test checkout')
        self.assertEqual(result['tasks'],1);self.assertTrue(self.db.import_workflow(self.root/'checkout','Exact test checkout')['replayed'])
        imported=self.db.latest_workflow();self.assertIsNone(imported['state']['deployment']['live_commit'])
        self.assertEqual(imported['tasks'][0]['status'],'blocked');self.assertEqual((folder/'tasks.json').read_bytes(),before)

    def test_changed_workflow_keeps_old_snapshot(self):
        folder,state,queue=self.workflow();self.db.import_workflow(self.root/'checkout','Test 1')
        queue['tasks'][0]['status']='ready';(folder/'tasks.json').write_text(json.dumps(queue))
        self.db.import_workflow(self.root/'checkout','Test 2')
        self.assertEqual(self.db.status()['workflow_snapshots'],2);self.assertEqual(self.db.latest_workflow()['tasks'][0]['status'],'ready')

    def test_bad_workflow_makes_no_partial_import(self):
        folder,state,queue=self.workflow();queue['tasks']*=2;(folder/'tasks.json').write_text(json.dumps(queue))
        with self.assertRaises(ValueError):self.db.import_workflow(self.root/'checkout','Test')
        self.assertEqual(self.db.status()['workflow_snapshots'],0);self.assertEqual(self.db.status()['sources'],1)

    def test_history_replay_and_active_to_completed_snapshot(self):
        folder,_,_=self.workflow();sessions=folder/'sessions';sessions.mkdir()
        session={'schema_version':1,'id':'test-session','status':'active','started_at':'2026-10-04T00:00:00Z','ended_at':None,'application':'ChatGPT Work / Codex','application_identity':'declared','summary':'','task_ids':['WF-001']}
        file=sessions/'test-session.json';file.write_text(json.dumps(session))
        self.assertEqual(self.db.import_history(self.root/'checkout','Test sessions')['added'],1)
        self.assertEqual(self.db.import_history(self.root/'checkout','Test sessions')['replayed'],1)
        session.update(status='completed',ended_at='2026-10-04T01:00:00Z',summary='Completed test')
        file.write_text(json.dumps(session));self.db.import_history(self.root/'checkout','Test sessions')
        self.assertEqual(len(self.db.events()),2)

    def test_backup_contains_wal_commits_and_history(self):
        self.db.put(self.record);self.db.put(dict(self.record,body='New body'),1)
        backup=self.root/'backups'/'copy.sqlite3';self.db.backup(backup)
        copy=ai.Database(backup)
        try:self.assertEqual(copy.get('rule')['body'],'New body');self.assertEqual(len(copy.history('rule')),2)
        finally:copy.close()
        with self.assertRaises(ValueError):self.db.backup(backup)

    def test_customer_database_is_never_adopted_or_modified(self):
        portal=self.root/'portal.sqlite';foreign=sqlite3.connect(portal);foreign.execute('CREATE TABLE users(id TEXT)');foreign.commit();foreign.close()
        before=portal.read_bytes()
        with self.assertRaises(ValueError):ai.Database(portal,create=True)
        self.assertEqual(portal.read_bytes(),before)

    def test_future_schema_refused(self):
        self.db.db.execute('PRAGMA user_version=900')
        with self.assertRaises(ValueError):ai.Database(self.path)

    def test_symlink_database_and_json_input_refused(self):
        link=self.root/'link.sqlite3'
        try:link.symlink_to(self.path)
        except OSError:self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError):ai.Database(link)
        data=self.root/'data.json';data.write_text('{}');alias=self.root/'alias.json';alias.symlink_to(data)
        with self.assertRaises(ValueError):ai.read_json(alias)

    def test_duplicate_json_keys_and_nonfinite_values_refused(self):
        file=self.root/'invalid.json'
        for content in ('{"id":"a","id":"b"}','{"value":NaN}'):
            file.write_text(content)
            with self.assertRaises(ValueError):ai.read_json(file)

    def test_report_escapes_text_and_export_includes_history(self):
        self.db.put(dict(self.record,title='<script>alert(1)</script>',body='<img src=x onerror=alert(2)>'))
        report=ai.report(self.db)
        self.assertNotIn('<script>alert(1)',report);self.assertNotIn('<img src=x',report)
        self.assertIn('&lt;script&gt;',report);self.assertIn('Owner build note',report)
        exported=self.db.export();self.assertEqual(len(exported['revisions']),1)

    def test_cli_init_search_and_private_context(self):
        import subprocess,sys
        subprocess.run([sys.executable,str(MODULE),'--db',str(self.path),'status'],check=True,capture_output=True)
        self.db.put(self.record)
        result=subprocess.run([sys.executable,str(MODULE),'--db',str(self.path),'context','laser'],check=True,capture_output=True,text=True)
        value=json.loads(result.stdout);self.assertIn('untrusted',value['instruction']);self.assertEqual(value['records'][0]['id'],'rule')


if __name__=='__main__':unittest.main()
