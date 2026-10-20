"""Sandbox installation must never reuse or overwrite production records."""
import hashlib
import importlib.util
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'deploy/hostinger/checkout-sandbox.py'


class CheckoutSandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.domain = Path(self.temp.name) / 'mirroriedled.com'
        self.domain.mkdir(mode=0o700)
        self.web = self.domain / 'public_html'
        self.web.mkdir()
        (self.web / 'index.html').write_text('production homepage')
        private = self.domain / 'mirroriedled-private/customer-portal'
        private.mkdir(parents=True, mode=0o700)
        (private / 'config.php').write_text('production config')
        (private / 'customer.sqlite').write_bytes(b'production records')
        self.old = {str(p.relative_to(self.domain)): p.read_bytes() for p in self.domain.rglob('*') if p.is_file()}
        self.creds = Path(self.temp.name) / 'credentials.json'
        self.creds.write_text(json.dumps({'stripe_secret_key': 'rk_test_Fixture123'}))
        self.archive = Path(self.temp.name) / 'website.zip'

    def helper(self):
        self.assertTrue(SCRIPT.is_file(), 'Missing isolated sandbox installer')
        spec = importlib.util.spec_from_file_location('checkout_sandbox', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def package(self, module):
        manifest = ''
        with zipfile.ZipFile(self.archive, 'w') as bundle:
            for name in module.release.PUBLIC_FILES:
                data = (ROOT / name).read_bytes()
                bundle.writestr(name, data)
                manifest += hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
            bundle.writestr(module.release.MANIFEST, manifest)

    def install(self, module):
        self.package(module)
        return module.install(self.web, self.archive, self.creds,
                              ROOT / 'customer-portal/backend/config.example.php', 'a' * 40)

    def test_install_preserves_production_and_isolates_private_configuration(self):
        module = self.helper()
        result = self.install(module)
        stage = self.web / 'MLED_checkout_TEST'
        private = self.domain / 'mirroriedled-private/checkout-sandbox'
        for path, data in self.old.items():
            self.assertEqual((self.domain / path).read_bytes(), data)
        self.assertIs(result['payments_enabled'], False)
        self.assertTrue((stage / 'shop/index.html').is_file())
        api = (stage / 'customer-portal/backend/api.php').read_text()
        self.assertIn('MLED_PORTAL_CONFIG', api)
        self.assertIn('/mirroriedled-private/checkout-sandbox/config.php', api)
        self.assertNotIn('rk_test_Fixture123', api)
        self.assertEqual(os.stat(private / 'credentials.json').st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(private).st_mode & 0o777, 0o700)
        for path in stage.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'rk_test_Fixture123', path.read_bytes())
        self.assertIn('SANDBOX', (stage / 'shop/index.html').read_text())
        self.assertNotIn("'mled_pending_build'", (stage / 'shop/shop.js').read_text())
        for script in ['app.js', 'shop/shop.js', 'infinity-builder/builder.js', 'address-builder/builder.js']:
            self.assertNotIn("'mirroriedled_storefront_cart_vnext'", (stage / script).read_text())
        self.assertNotIn("'mirroriedled_infinity_drafts_v1'", (stage / 'infinity-builder/draft-store.js').read_text())
        self.assertNotIn("'mledStadiumTestSelectionV1'", (stage / 'stadiums/stadiums.js').read_text())
        command = ['php', '-r', '$c=require $argv[1]; echo json_encode(["mode"=>$c["commerce"]["mode"],"enabled"=>$c["commerce"]["enabled"],"staff"=>$c["staff_users"],"storage"=>$c["storage_path"]]);', str(private / 'config.php')]
        configured = json.loads(subprocess.check_output(command, text=True))
        self.assertEqual(configured['mode'], 'test')
        self.assertIs(configured['enabled'], False)
        self.assertEqual(configured['staff'], [])
        self.assertEqual(configured['storage'], str(private / 'storage'))

    def test_existing_stage_is_never_overwritten(self):
        module = self.helper()
        target = self.web / 'MLED_checkout_TEST'
        target.mkdir()
        (target / 'keep').write_text('existing stage')
        with self.assertRaises(ValueError):
            self.install(module)
        self.assertEqual((target / 'keep').read_text(), 'existing stage')

    def test_webhook_secret_install_is_private_idempotent_and_keeps_checkout_off(self):
        module = self.helper()
        self.install(module)
        public_before = {str(p): p.read_bytes() for p in self.web.rglob('*') if p.is_file()}
        private = self.domain / 'mirroriedled-private/checkout-sandbox'
        (private / 'storage/keep.sqlite').write_bytes(b'sandbox records')
        result = module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_FixtureSigner123'})
        self.assertIs(result['webhook_signing_secret_installed'], True)
        self.assertIs(result['payments_enabled'], False)
        self.assertIs(result['signed_delivery_verified'], False)
        for path, data in self.old.items():
            self.assertEqual((self.domain / path).read_bytes(), data)
        self.assertEqual(public_before, {str(p): p.read_bytes() for p in self.web.rglob('*') if p.is_file()})
        self.assertEqual((private / 'storage/keep.sqlite').read_bytes(), b'sandbox records')
        command = ['php', '-r', '$c=require $argv[1]; echo json_encode(["secret"=>$c["commerce"]["stripe_webhook_secret"],"mode"=>$c["commerce"]["mode"],"enabled"=>$c["commerce"]["enabled"],"tax"=>$c["commerce"]["tax_setup_confirmed"],"fulfillment"=>$c["commerce"]["fulfillment_setup_confirmed"]]);', str(private / 'config.php')]
        self.assertEqual(json.loads(subprocess.check_output(command, text=True)), {'secret': 'whsec_FixtureSigner123', 'mode': 'test', 'enabled': False, 'tax': False, 'fulfillment': False})
        self.assertEqual((private / 'credentials.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((private / 'config.php').stat().st_mode & 0o777, 0o600)
        module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_FixtureSigner123'})
        self.assertNotIn('whsec_FixtureSigner123', json.dumps(result))

    def test_webhook_install_refuses_wrong_secret_and_preserves_files(self):
        module = self.helper()
        self.install(module)
        private = self.domain / 'mirroriedled-private/checkout-sandbox'
        before = {str(p): p.read_bytes() for p in private.rglob('*') if p.is_file()}
        for value in ['', 'rk_test_Fixture', 'whsec_Fixture\n', 'whsec_']:
            with self.assertRaises(ValueError):
                module.install_webhook_secret(self.web, {'stripe_webhook_secret': value})
        self.assertEqual(before, {str(p): p.read_bytes() for p in private.rglob('*') if p.is_file()})

    def test_signer_workflow_executes_its_php_verification_script(self):
        module = self.helper()
        self.install(module)
        module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_WorkflowFixture'})
        workflow = (ROOT / '.github/workflows/install-sandbox-webhook-secret.yml').read_text()
        line = next(line for line in workflow.splitlines() if '"php -- ' in line)
        remote = 'php -- ' + line.split('"php -- ', 1)[1].split('" <<', 1)[0]
        command = shlex.split(remote.replace('${PUBLIC_HTML%/public_html}', str(self.domain)))
        script = textwrap.dedent(workflow.split("<<'PHPVERIFY'\n", 1)[1].split('          PHPVERIFY', 1)[0])
        result = subprocess.run(command, input=script, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'MLED_SANDBOX_SIGNER_CONFIG_VERIFIED=true\n')

    def test_webhook_install_does_not_rotate_an_existing_different_secret(self):
        module = self.helper()
        self.install(module)
        module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_FirstFixture'})
        private = self.domain / 'mirroriedled-private/checkout-sandbox'
        before = (private / 'credentials.json').read_bytes()
        with self.assertRaises(ValueError):
            module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_OtherFixture'})
        self.assertEqual((private / 'credentials.json').read_bytes(), before)

    def test_interrupted_signer_update_can_recover_with_same_secret(self):
        module = self.helper()
        self.install(module)
        code = '''import importlib.util, os, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('interrupted_sandbox',sys.argv[1])
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
replace=m.os.replace
def interrupt(*args):
    replace(*args)
    os._exit(23)
m.os.replace=interrupt
m.install_webhook_secret(Path(sys.argv[2]), {'stripe_webhook_secret':'whsec_RecoveryFixture'})
'''
        result = subprocess.run([sys.executable, '-c', code, str(SCRIPT), str(self.web)], capture_output=True)
        self.assertEqual(result.returncode, 23)
        result = module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_RecoveryFixture'})
        self.assertIs(result['webhook_signing_secret_installed'], True)

    def test_webhook_install_refuses_modified_configuration(self):
        module = self.helper()
        self.install(module)
        private = self.domain / 'mirroriedled-private/checkout-sandbox'
        config = private / 'config.php'
        config.write_text(config.read_text().replace("'enabled' => false", "'enabled' => true"))
        before = (private / 'credentials.json').read_bytes()
        with self.assertRaises(ValueError):
            module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_Fixture'})
        self.assertEqual((private / 'credentials.json').read_bytes(), before)

    def test_webhook_install_refuses_unsafe_credentials_and_public_root(self):
        module = self.helper()
        self.install(module)
        private = self.domain / 'mirroriedled-private/checkout-sandbox'
        credentials = private / 'credentials.json'
        original = credentials.read_bytes()
        credentials.unlink()
        credentials.symlink_to(self.creds)
        with self.assertRaises(ValueError):
            module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_Fixture'})
        credentials.unlink()
        credentials.write_bytes(original)
        credentials.chmod(0o644)
        with self.assertRaises(ValueError):
            module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_Fixture'})
        credentials.chmod(0o600)
        self.web.chmod(0o777)
        with self.assertRaises(ValueError):
            module.install_webhook_secret(self.web, {'stripe_webhook_secret': 'whsec_Fixture'})

    def test_generated_api_selects_sandbox_even_with_production_environment_override(self):
        module = self.helper()
        self.install(module)
        api = self.web / 'MLED_checkout_TEST/customer-portal/backend/api.php'
        production_config = self.domain / 'mirroriedled-private/customer-portal/config.php'
        code = '''putenv('MLED_PORTAL_CONFIG='.$argv[3]);
$_SERVER['DOCUMENT_ROOT']=$argv[2]; $_SERVER['HTTPS']='on';
$_SERVER['SERVER_PORT']='443'; $_SERVER['HTTP_HOST']='mirroriedled.com';
$_SERVER['REMOTE_ADDR']='127.0.0.1'; $_SERVER['REQUEST_METHOD']='GET';
$_SERVER['SCRIPT_NAME']='/MLED_checkout_TEST/customer-portal/backend/api.php';
$_GET['action']='session'; require $argv[1];'''
        data = json.loads(subprocess.check_output(['php', '-r', code, str(api), str(self.web), str(production_config)], text=True))
        self.assertIs(data['configured'], True)
        self.assertIs(data['capabilities']['payments'], False)
        self.assertTrue((self.domain / 'mirroriedled-private/checkout-sandbox/storage/portal.sqlite').is_file())
        self.assertEqual(production_config.read_text(), 'production config')

    def test_group_writable_domain_parent_is_refused(self):
        module = self.helper()
        self.domain.chmod(0o770)
        with self.assertRaises(ValueError):
            self.install(module)
        self.assertFalse((self.web / 'MLED_checkout_TEST').exists())

    def test_group_writable_public_root_is_refused(self):
        module = self.helper()
        self.web.chmod(0o770)
        with self.assertRaises(ValueError):
            self.install(module)
        self.assertFalse((self.web / 'MLED_checkout_TEST').exists())

    def test_failed_transport_creation_does_not_arm_remote_cleanup(self):
        workflow = (ROOT / '.github/workflows/deploy-checkout-sandbox.yml').read_text()
        block = workflow.split('      - name: Install only the isolated sandbox folder')[1].split('      - name: Verify exact sandbox')[0]
        script = textwrap.dedent(block.split('        run: |\n', 1)[1])
        binary = Path(self.temp.name) / 'bin'
        binary.mkdir()
        ssh = binary / 'ssh'
        ssh.write_text('#!/bin/sh\nexit 1\n')
        ssh.chmod(0o700)
        output = Path(self.temp.name) / 'github-env'
        output.touch()
        env = os.environ.copy()
        env.update(PATH=str(binary) + ':' + env['PATH'], PUBLIC_HTML=str(self.web),
                   GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1', GITHUB_SHA='a'*40,
                   RUNNER_TEMP=self.temp.name, GITHUB_ENV=str(output), SSH_PORT='22',
                   SSH_HOST='example.invalid', SSH_USER='fixture', REMOTE_PYTHON='python3')
        result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('REMOTE_SANDBOX_STAGE=', output.read_text())

    def test_live_key_is_rejected_without_creating_a_stage(self):
        module = self.helper()
        self.creds.write_text(json.dumps({'stripe_secret_key': 'rk_live_Fixture123'}))
        with self.assertRaises(ValueError):
            self.install(module)
        self.assertFalse((self.web / 'MLED_checkout_TEST').exists())

    def test_private_parent_or_stage_symlink_is_refused(self):
        module = self.helper()
        for name in ['MLED_checkout_TEST']:
            target = self.web / name
            target.symlink_to(self.domain / 'mirroriedled-private', target_is_directory=True)
            with self.assertRaises(ValueError):
                self.install(module)
            target.unlink()
        private = self.domain / 'mirroriedled-private/checkout-sandbox'
        private.symlink_to(self.domain / 'mirroriedled-private/customer-portal', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.install(module)
        self.assertFalse((self.web / 'MLED_checkout_TEST').exists())

    def test_corrupt_bundle_fails_before_publication(self):
        module = self.helper()
        self.archive.write_bytes(b'invalid zip')
        with self.assertRaises(Exception):
            module.install(self.web, self.archive, self.creds, ROOT / 'customer-portal/backend/config.example.php', 'a' * 40)
        self.assertFalse((self.web / 'MLED_checkout_TEST').exists())


if __name__ == '__main__':
    unittest.main()
