"""Private Google OAuth storage and browser-bound authorization (lazy dependencies)."""
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from urllib.parse import urlsplit

AUTH_URI = 'https://accounts.google.com/o/oauth2/auth'
TOKEN_URI = 'https://oauth2.googleapis.com/token'
LOOPBACK_HOSTS = frozenset({'localhost', '127.0.0.1', '::1'})
SCOPES = ['https://www.googleapis.com/auth/drive']
_LOCK = threading.RLock()


class DriveError(RuntimeError):
    """Safe user-facing error; never include upstream response bodies."""


def normalize_client_config(value):
    web = value.get('web') if isinstance(value, dict) else None
    if not isinstance(web, dict) or any(not isinstance(web.get(k), str) or not web[k].strip()
                                        for k in ('client_id', 'client_secret')):
        raise DriveError('Import a Google web OAuth client JSON with client_id and client_secret.')
    for key, expected in [('auth_uri', AUTH_URI), ('token_uri', TOKEN_URI)]:
        if web.get(key, expected) != expected:
            raise DriveError('Only official Google OAuth endpoints are supported.')
    return {'web': {k: web[k].strip() for k in ('client_id', 'client_secret')} |
            {'auth_uri': AUTH_URI, 'token_uri': TOKEN_URI}}


def validate_redirect_uri(value):
    if not isinstance(value, str):
        raise DriveError('Enter an HTTPS callback URL, or HTTP for localhost.')
    try:
        u = urlsplit(value.strip())
        local_http = u.scheme == 'http' and u.hostname in LOOPBACK_HOSTS
        if ((u.scheme != 'https' and not local_http) or not u.hostname or u.username or u.password or
                u.fragment or u.query or not u.path.endswith('/google_drive_upload/oauth/callback')):
            raise ValueError()
        _ = u.port
    except ValueError:
        raise DriveError('Use HTTPS (or HTTP on localhost, 127.0.0.1, or ::1) ending in /google_drive_upload/oauth/callback, without query or fragment.') from None
    return value.strip()


class DriveStore:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = _LOCK

    def _prepare(self):
        if self.root.is_symlink():
            raise DriveError('Google Drive credential directory must not be a symbolic link.')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def _read(self, name):
        self._prepare()
        path = self.root / name
        if path.is_symlink():
            raise DriveError('Google Drive credential files must not be symbolic links.')
        if not path.exists():
            return None
        try:
            result = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, OSError):
            raise DriveError('Google Drive configuration could not be read. Open Google Drive Setup.') from None

    def _write(self, name, value):
        self._prepare()
        fd, tmp = tempfile.mkstemp(prefix='.drive-', dir=self.root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(value, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.root / name)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def save_config(self, client_json, redirect_uri):
        config = {'client': normalize_client_config(client_json),
                  'redirect_uri': validate_redirect_uri(redirect_uri),
                  'revision': secrets.token_urlsafe(24)}
        with self.lock:
            self._write('config.json', config)
            self._write('token.json', {})

    def load_config(self):
        with self.lock:
            config = self._read('config.json')
            if not config:
                raise DriveError('Open Google Drive Setup and save OAuth credentials first.')
            return config

    def load_token(self):
        with self.lock:
            return self._read('token.json') or None

    def save_token(self, token):
        with self.lock:
            current = self.load_token() or {}
            merged = dict(token)
            if not merged.get('refresh_token') and current.get('refresh_token'):
                merged['refresh_token'] = current['refresh_token']
            self._write('token.json', merged)

    def status(self):
        with self.lock:
            config = self._read('config.json') or {}
            token = self.load_token() or {}
            return {'configured': bool(config), 'connected': bool(token.get('refresh_token')),
                    'redirect_uri': config.get('redirect_uri', '')}


def _flow(config, **kwargs):
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        raise DriveError('Install requirements.txt with the Python used by ComfyUI, then restart.') from None
    return Flow.from_client_config(config['client'], scopes=SCOPES,
                                   redirect_uri=config['redirect_uri'], **kwargs)


class OAuthSessions:
    def __init__(self, store):
        self.store = store
        self.pending = {}
        self.lock = threading.RLock()

    def begin(self, browser_id):
        config = self.store.load_config()
        flow = _flow(config, autogenerate_code_verifier=True)
        url, state = flow.authorization_url(access_type='offline', prompt='consent')
        now = time.monotonic()
        with self.lock:
            self.pending = {s: e for s, e in self.pending.items() if now < e['expires']}
            if len(self.pending) >= 100:
                raise DriveError('Too many pending connections. Wait ten minutes and retry.')
            self.pending[state] = {'browser': browser_id, 'config': config,
                                   'verifier': flow.code_verifier, 'expires': now + 600}
        return {'authorization_url': url}

    def consume(self, state, browser_id):
        with self.lock:
            entry = self.pending.get(state)
            if not entry or not secrets.compare_digest(entry['browser'], browser_id or ''):
                raise DriveError('Invalid OAuth session. Connect Google Drive again in the same browser.')
            del self.pending[state]
        if (entry['expires'] <= time.monotonic() or
                entry['config']['revision'] != self.store.load_config()['revision']):
            raise DriveError('OAuth session expired or configuration changed. Connect again.')
        return entry

    def complete(self, state, browser_id, code):
        entry = self.consume(state, browser_id)
        if not code:
            raise DriveError('Google authorization was cancelled. Connect again when ready.')
        try:
            flow = _flow(entry['config'], state=state, code_verifier=entry['verifier'])
            flow.fetch_token(code=code, timeout=30)
            token = json.loads(flow.credentials.to_json())
            if not token.get('refresh_token'):
                raise DriveError('Google did not return offline access. Revoke the app in your Google account and connect again.')
            with self.store.lock:
                if self.store.load_config()['revision'] != entry['config']['revision']:
                    raise DriveError('Configuration changed during sign-in. Connect again.')
                self.store.save_token(token)
        except DriveError:
            raise
        except Exception:
            raise DriveError('Google sign-in failed. Check the exact registered callback URL and reconnect.') from None


_store = None
_sessions = None


def get_drive_store():
    global _store
    with _LOCK:
        if _store is None:
            import folder_paths
            _store = DriveStore(Path(folder_paths.get_user_directory()) / 'google_drive_upload')
        return _store


def get_oauth_sessions():
    global _sessions
    with _LOCK:
        if _sessions is None:
            _sessions = OAuthSessions(get_drive_store())
        return _sessions
