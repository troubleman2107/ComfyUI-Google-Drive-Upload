"""Run: python -m unittest discover -s scripts -p 'google_drive*_test.py' -v"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nodes'))
import _google_drive_helpers as gd

CLIENT = {'web': {'client_id': 'test.apps.googleusercontent.com', 'client_secret': 'test-secret'}}
CALLBACK = 'https://comfy.example/prefix/api/google_drive_upload/oauth/callback'

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = gd.DriveStore(Path(self.tmp.name) / 'drive')

    def test_config_validation(self):
        self.store.save_config(CLIENT, CALLBACK)
        self.assertEqual(self.store.load_config()['redirect_uri'], CALLBACK)
        for client in [{}, {'web': {}}, {'web': {**CLIENT['web'], 'token_uri': 'https://evil.example/token'}}]:
            with self.assertRaises(gd.DriveError):
                self.store.save_config(client, CALLBACK)
        for url in ['http://comfy.example/callback', 'https://user:pass@host/callback', CALLBACK+'#secret', CALLBACK+'?x=1']:
            with self.assertRaises(gd.DriveError):
                gd.validate_redirect_uri(url)

    def test_private_status_and_token_update(self):
        self.store.save_config(CLIENT, CALLBACK)
        self.store.save_token({'refresh_token':'refresh-secret','token':'access-secret'})
        self.store.save_token({'token':'new-access'})
        self.assertEqual(self.store.load_token()['refresh_token'], 'refresh-secret')
        status = self.store.status()
        self.assertTrue(status['connected'])
        self.assertNotIn('secret', json.dumps(status))
        if os.name != 'nt':
            self.assertEqual(self.store.root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((self.store.root/'token.json').stat().st_mode & 0o777, 0o600)
        self.store.save_config(CLIENT, CALLBACK)
        self.assertIsNone(self.store.load_token(), 'Reconfiguration invalidates old tokens')

    def test_symlink_rejected(self):
        target = Path(self.tmp.name)/'other'
        target.mkdir()
        self.store.root.symlink_to(target, target_is_directory=True)
        with self.assertRaises(gd.DriveError):
            self.store.save_config(CLIENT, CALLBACK)

class SessionTests(StoreTests):
    def test_browser_expiry_and_replay(self):
        self.store.save_config(CLIENT, CALLBACK)
        sessions = gd.OAuthSessions(self.store)
        result = sessions.begin('browser-a')
        from urllib.parse import urlsplit, parse_qs
        query = parse_qs(urlsplit(result['authorization_url']).query)
        state = query['state'][0]
        self.assertEqual(query['access_type'], ['offline'])
        self.assertIn('code_challenge', query)
        self.assertEqual(query['redirect_uri'], [CALLBACK])
        with self.assertRaises(gd.DriveError):
            sessions.consume(state, 'browser-b')
        entry = sessions.consume(state, 'browser-a')
        self.assertEqual(entry['config']['redirect_uri'], CALLBACK)
        with self.assertRaises(gd.DriveError):
            sessions.consume(state, 'browser-a')
        second = sessions.begin('browser-a')
        state = parse_qs(urlsplit(second['authorization_url']).query)['state'][0]
        with patch.object(gd.time, 'monotonic', return_value=10**20):
            with self.assertRaises(gd.DriveError): sessions.consume(state, 'browser-a')

    def test_reconfiguration_invalidates_state(self):
        self.store.save_config(CLIENT, CALLBACK)
        sessions = gd.OAuthSessions(self.store)
        from urllib.parse import urlsplit, parse_qs
        state = parse_qs(urlsplit(sessions.begin('a')['authorization_url']).query)['state'][0]
        self.store.save_config(CLIENT, CALLBACK)
        with self.assertRaises(gd.DriveError): sessions.consume(state, 'a')

    def test_exchange_preserves_secrets_on_server(self):
        self.store.save_config(CLIENT, CALLBACK)
        sessions = gd.OAuthSessions(self.store)
        entry = {'config': self.store.load_config(), 'verifier': 'pkce'}
        flow = Mock()
        flow.credentials.to_json.return_value = json.dumps({'refresh_token':'private-refresh','token':'private-token'})
        with patch.object(sessions, 'consume', return_value=entry), patch.object(gd, '_flow', return_value=flow):
            sessions.complete('state','browser','code')
        flow.fetch_token.assert_called_once_with(code='code', timeout=30)
        self.assertEqual(self.store.load_token()['refresh_token'], 'private-refresh')
        flow.fetch_token.side_effect = RuntimeError('private-response-with-token')
        with patch.object(sessions, 'consume', return_value=entry), patch.object(gd, '_flow', return_value=flow):
            with self.assertRaises(gd.DriveError) as raised: sessions.complete('state','browser','code')
        self.assertNotIn('private', str(raised.exception))

    def test_denied_and_missing_offline_token(self):
        self.store.save_config(CLIENT, CALLBACK)
        sessions = gd.OAuthSessions(self.store)
        entry = {'config': self.store.load_config(), 'verifier':'pkce'}
        with patch.object(sessions, 'consume', return_value=entry):
            with self.assertRaisesRegex(gd.DriveError, 'cancelled'): sessions.complete('s','b','')
        flow=Mock();flow.credentials.to_json.return_value='{"token":"access-only"}'
        with patch.object(sessions, 'consume', return_value=entry), patch.object(gd, '_flow', return_value=flow):
            with self.assertRaisesRegex(gd.DriveError, 'offline'): sessions.complete('s','b','code')
        self.assertIsNone(self.store.load_token())

if __name__ == '__main__': unittest.main()
