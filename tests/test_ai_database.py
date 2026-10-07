"""Behavior tests for private knowledge, provenance, revisions and durable imports."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

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

    def session_file(self,session_id='test-session',started='2026-10-04T00:00:00Z',ended='2026-10-04T01:00:00Z'):
        folder=self.root/'checkout'/'docs'/'ai-workflow'/'sessions';folder.mkdir(parents=True,exist_ok=True)
        session={'schema_version':1,'id':session_id,'status':'completed','started_at':started,'ended_at':ended,
                 'application':'ChatGPT Work / Codex','application_identity':'declared','summary':'Completed test','task_ids':['WF-001']}
        (folder/(session_id+'.json')).write_text(json.dumps(session))
        return session

    def hot_journal(self,path):
        connection=sqlite3.connect(path)
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.execute('CREATE TABLE recovery_fixture(body TEXT)')
        connection.executemany('INSERT INTO recovery_fixture VALUES(?)',[('A'*10000,)]*20)
        connection.commit();connection.close()
        child="""import os,sqlite3,sys
connection=sqlite3.connect(sys.argv[1],isolation_level=None)
connection.execute('PRAGMA cache_size=1')
connection.execute('BEGIN IMMEDIATE')
connection.execute("UPDATE recovery_fixture SET body = printf('%010000d', 2)")
os._exit(0)
"""
        subprocess.run([sys.executable,'-c',child,str(path)],check=True,capture_output=True)
        journal=Path(str(path)+'-journal')
        self.assertTrue(journal.is_file())
        self.assertNotEqual(journal.read_bytes()[:8],b'\0'*8)
        return journal

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

    def test_original_strings_reject_bearer_whitespace_before_persistence(self):
        value='synthetic-bearer-credential'
        index=0
        for separator in ('\t','\n'):
            for location in ('body','nested_value','nested_key'):
                with self.subTest(separator=repr(separator),location=location):
                    candidate=dict(self.record,id='unsafe-'+str(index));index+=1
                    credential='Bearer'+separator+value
                    if location=='body':candidate['body']=credential
                    elif location=='nested_value':candidate['metadata']={'nested':[{'value':credential}]}
                    else:candidate['metadata']={credential:'safe text'}
                    with self.assertRaises(ValueError):self.db.put(candidate)
        self.assertEqual(self.db.status()['record_counts'],{})
        self.assertNotIn(value,ai.dumps(self.db.export()))

    def test_mixed_case_credential_urls_are_refused_but_public_urls_remain_valid(self):
        unsafe=['HTTPS://example.com/file?signature=synthetic-link-value',
                'HtTpS://example.com/file?access_code=synthetic-link-value',
                'HTTP://synthetic-user:synthetic-password@example.com/file']
        for index,body in enumerate(unsafe):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):self.db.put(dict(self.record,id='unsafe-url-'+str(index),body=body))
        self.db.put(dict(self.record,id='public-url',body='HTTPS://example.com/public/file'))
        self.assertEqual(self.db.status()['record_counts'],{'knowledge':1})
        self.assertNotIn('synthetic-link-value',ai.dumps(self.db.export()))
        self.assertNotIn('synthetic-password',ai.dumps(self.db.export()))

    def test_product_bundle_replay_rejects_boolean_cost_without_changing_record(self):
        product=dict(self.record,id='product',kind='product',metadata={'cost_usd':1,'price_basis':'owner_cost','cost_as_of':'2026-10-06'})
        self.db.bundle({'sources':[self.source],'records':[product]})
        changed=dict(product,metadata={**product['metadata'],'cost_usd':True})
        with self.assertRaises(ValueError):self.db.bundle({'sources':[],'records':[changed]})
        stored=self.db.get('product')
        self.assertIs(type(stored['metadata']['cost_usd']),int)
        self.assertEqual(stored['version'],1)
        self.assertEqual(len(self.db.history('product')),1)

    def test_bundle_replay_distinguishes_nested_json_boolean_and_number_types(self):
        record=dict(self.record,metadata={'nested':[{'enabled':1}]})
        self.db.bundle({'sources':[],'records':[record]})
        with self.assertRaises(ValueError):
            self.db.bundle({'sources':[],'records':[dict(record,metadata={'nested':[{'enabled':True}]})]})
        self.assertEqual(self.db.get('rule')['metadata'],{'nested':[{'enabled':1}]})
        self.assertEqual(len(self.db.history('rule')),1)

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

    def test_history_accepts_forward_fractional_second_and_retains_timestamp(self):
        session=self.session_file(ended='2026-10-04T00:00:00.500Z')
        self.assertEqual(self.db.import_history(self.root/'checkout','CLI sessions'),{'added':1,'replayed':0})
        event=self.db.events()[0]
        self.assertEqual(event['occurred_at'],session['ended_at'])
        self.assertEqual(event['details']['source_snapshot']['started_at'],session['started_at'])
        source=self.db.db.execute('SELECT observed_at FROM sources WHERE id=?',(event['source_id'],)).fetchone()
        self.assertEqual(source['observed_at'],session['ended_at'])

    def test_history_rejects_reversed_fractional_second_without_partial_import(self):
        self.session_file(started='2026-10-04T00:00:00.500Z',ended='2026-10-04T00:00:00Z')
        before=self.db.status()
        with self.assertRaisesRegex(ValueError,'ends before'):self.db.import_history(self.root/'checkout','CLI sessions')
        self.assertEqual(self.db.status(),before)

    def test_history_overlap_from_new_locator_preserves_original_provenance(self):
        self.session_file(session_id='first-session')
        self.assertEqual(self.db.import_history(self.root/'checkout','CLI sessions'),{'added':1,'replayed':0})
        original=self.db.events()[0]
        self.session_file(session_id='second-session')
        self.assertEqual(self.db.import_history(self.root/'checkout','Packaged launcher'),{'added':1,'replayed':1})
        exported=self.db.export();sources={source['id']:source for source in exported['sources']}
        by_session={event['details']['session_id']:event for event in exported['activity']}
        self.assertEqual(by_session['first-session'],original)
        self.assertEqual(sources[original['source_id']]['locator'],'CLI sessions/first-session.json')
        self.assertEqual(sources[by_session['second-session']['source_id']]['locator'],'Packaged launcher/second-session.json')
        self.assertEqual(len(exported['activity']),2)
        self.assertEqual(len(exported['sources']),3)

    def test_concurrent_history_imports_preserve_one_event_and_source(self):
        self.session_file();barrier=Barrier(2)
        def import_from(locator):
            db=ai.Database(self.path)
            try:
                barrier.wait(timeout=10)
                return db.import_history(self.root/'checkout',locator)
            finally:db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(import_from,['CLI sessions','Packaged launcher']))
        self.assertEqual(sorted((result['added'],result['replayed']) for result in results),[(0,1),(1,0)])
        self.assertEqual(self.db.status()['activity'],1)
        self.assertEqual(self.db.status()['sources'],2)
        event=self.db.events()[0]
        source=self.db.db.execute('SELECT locator FROM sources WHERE id=?',(event['source_id'],)).fetchone()
        self.assertIn(source['locator'],{'CLI sessions/test-session.json','Packaged launcher/test-session.json'})

    def test_history_request_id_conflict_leaves_no_orphan_source(self):
        session=self.session_file();checksum=hashlib.sha256(ai.dumps(session).encode()).hexdigest()
        self.db.event({'request_id':'session-'+checksum,'action':'manual-note','summary':'Different activity','source_id':'src'})
        before=self.db.export()
        with self.assertRaisesRegex(ValueError,'Request ID reused'):
            self.db.import_history(self.root/'checkout','CLI sessions')
        after=self.db.export()
        self.assertEqual(after['sources'],before['sources'])
        self.assertEqual(after['activity'],before['activity'])

    def test_invalid_history_activity_leaves_no_orphan_source(self):
        session=self.session_file();session['application']=42
        file=self.root/'checkout'/'docs'/'ai-workflow'/'sessions'/'test-session.json'
        file.write_text(json.dumps(session));before=self.db.status()
        with self.assertRaisesRegex(ValueError,'Invalid application'):
            self.db.import_history(self.root/'checkout','CLI sessions')
        self.assertEqual(self.db.status(),before)

    def test_backup_contains_wal_commits_and_history(self):
        self.db.put(self.record);self.db.put(dict(self.record,body='New body'),1)
        backup=self.root/'backups'/'copy.sqlite3';self.db.backup(backup)
        copy=ai.Database(backup)
        try:self.assertEqual(copy.get('rule')['body'],'New body');self.assertEqual(len(copy.history('rule')),2)
        finally:copy.close()
        with self.assertRaises(ValueError):self.db.backup(backup)

    @unittest.skipIf(os.name=='nt','POSIX file modes do not configure Windows ACLs')
    def test_recognized_database_and_sidecars_are_private_before_wal_and_writes(self):
        self.db.put(self.record)
        files=[self.path,Path(str(self.path)+'-wal'),Path(str(self.path)+'-shm')]
        self.assertTrue(all(path.is_file() for path in files))
        for path in files:os.chmod(path,0o644)
        observed=[]
        connect=sqlite3.connect
        def authorizer(action,first,second,*unused):
            if action==sqlite3.SQLITE_PRAGMA and first.lower()=='journal_mode' and str(second).lower()=='wal':
                observed.append([stat.S_IMODE(path.stat().st_mode) for path in files])
            return sqlite3.SQLITE_OK
        def monitored_connect(*args,**kwargs):
            connection=connect(*args,**kwargs)
            connection.set_authorizer(authorizer)
            return connection
        with patch.object(ai.sqlite3,'connect',side_effect=monitored_connect):
            reopened=ai.Database(self.path)
        try:
            self.assertEqual(observed,[[0o600,0o600,0o600]])
            reopened.put(dict(self.record,id='second-record'))
            self.assertEqual([stat.S_IMODE(path.stat().st_mode) for path in files],[0o600,0o600,0o600])
            self.assertEqual(reopened.get('second-record')['body'],self.record['body'])
        finally:reopened.close()

    @unittest.skipIf(os.name=='nt','POSIX file modes do not configure Windows ACLs')
    def test_reopened_private_database_creates_private_new_sidecars(self):
        self.db.put(self.record)
        self.db.close()
        self.assertFalse(Path(str(self.path)+'-wal').exists())
        os.chmod(self.path,0o644)
        self.db=ai.Database(self.path)
        self.db.put(dict(self.record,id='new-record'))
        self.assertEqual([stat.S_IMODE(Path(str(self.path)+suffix).stat().st_mode) for suffix in ('','-wal','-shm')],[0o600]*3)

    @unittest.skipIf(os.name=='nt','POSIX file modes do not configure Windows ACLs')
    def test_recognized_hot_journal_is_protected_before_writable_open_and_recovery(self):
        path=self.root/'recognized.sqlite3';seed=ai.Database(path,create=True);seed.close()
        journal=self.hot_journal(path)
        for file in (path,journal):os.chmod(file,0o644)
        observations=[];connect=sqlite3.connect
        def monitored_connect(target,*args,**kwargs):
            if Path(target)==path:
                observations.append([stat.S_IMODE(file.stat().st_mode) for file in (path,journal)])
            return connect(target,*args,**kwargs)
        with patch.object(ai.sqlite3,'connect',side_effect=monitored_connect):
            recovered=ai.Database(path)
        try:
            self.assertEqual(observations,[[0o600,0o600]])
            rows=recovered.db.execute('SELECT body FROM recovery_fixture').fetchall()
            self.assertEqual([row['body'] for row in rows],['A'*10000]*20)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        finally:recovered.close()

    def test_unrelated_hot_journal_is_refused_without_recovery_or_changes(self):
        path=self.root/'foreign.sqlite3';journal=self.hot_journal(path)
        before={file:(file.read_bytes(),stat.S_IMODE(file.stat().st_mode)) for file in (path,journal)}
        with self.assertRaisesRegex(ValueError,'another database'):ai.Database(path,create=True)
        for file,(content,mode) in before.items():
            self.assertTrue(file.exists())
            self.assertEqual(file.read_bytes(),content)
            self.assertEqual(stat.S_IMODE(file.stat().st_mode),mode)

    def test_recognition_reads_application_metadata_from_active_wal(self):
        self.assertEqual(int.from_bytes(self.path.read_bytes()[68:72],'big'),0)
        self.assertTrue(Path(str(self.path)+'-wal').is_file())
        reopened=ai.Database(self.path)
        try:
            self.assertEqual(reopened.db.execute('PRAGMA application_id').fetchone()[0],ai.APP_ID)
            self.assertEqual(reopened.status()['sources'],1)
        finally:reopened.close()

    def test_customer_database_is_never_adopted_or_modified(self):
        portal=self.root/'portal.sqlite';foreign=sqlite3.connect(portal);foreign.execute('CREATE TABLE users(id TEXT)');foreign.commit();foreign.close()
        before=portal.read_bytes();mode=stat.S_IMODE(portal.stat().st_mode)
        with self.assertRaises(ValueError):ai.Database(portal,create=True)
        self.assertEqual(portal.read_bytes(),before)
        self.assertEqual(stat.S_IMODE(portal.stat().st_mode),mode)

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
