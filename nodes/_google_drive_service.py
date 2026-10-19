"""Google Drive operations. All API clients are private to one operation."""
import io
import json
import re
from ._google_drive_helpers import DriveError, SCOPES, TOKEN_URI, get_drive_store


def folder_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value.strip()):
        raise DriveError('Enter a folder ID from the Google Drive folder URL, not the full URL.')
    return value.strip()


def api_error(exc):
    status = getattr(getattr(exc, 'resp', None), 'status', None)
    if status == 401:
        return DriveError('Google authorization expired. Connect Google Drive again.')
    if status == 403:
        return DriveError('Google denied this operation. Check folder permissions and Drive storage quota.')
    if status == 404:
        return DriveError('Google Drive folder or file was not found or is not accessible.')
    return DriveError('Google Drive request failed or timed out. Check the connection and retry.')


class DriveService:
    def __init__(self, store=None):
        self.store = store or get_drive_store()
        try:
            import httplib2
            import google_auth_httplib2
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            raise DriveError('Install requirements.txt with the Python used by ComfyUI, then restart.') from None
        with self.store.lock:
            config = self.store.load_config()
            token = self.store.load_token() or {}
            if not token.get('refresh_token'):
                raise DriveError('Connect Google Drive from Google Drive Setup before uploading.')
            # Force known Google endpoints regardless of local token JSON contents.
            info = {**token, **config['client']['web']}
            info['token_uri'] = TOKEN_URI
            credentials = Credentials.from_authorized_user_info(info, scopes=SCOPES)
            if not credentials.valid:
                try:
                    request = Request()
                    credentials.refresh(lambda **kwargs: request(**dict(kwargs, timeout=30)))
                    self.store.save_token(json.loads(credentials.to_json()))
                except Exception:
                    raise DriveError('Could not refresh Google access. Connect Google Drive again.') from None
        # Refresh on this client is not persisted; the next operation can safely
        # refresh the stored token again. Each HTTP request has a finite timeout.
        try:
            http = google_auth_httplib2.AuthorizedHttp(credentials, http=httplib2.Http(timeout=30))
            self.api = build('drive', 'v3', http=http, cache_discovery=False, static_discovery=True)
        except Exception:
            raise DriveError('Could not initialize Google Drive. Check optional dependencies.') from None

    def validate_folder(self, value):
        value = folder_id(value)
        try:
            info = self.api.files().get(fileId=value, supportsAllDrives=True, fields='id,mimeType,trashed,capabilities(canAddChildren)').execute(num_retries=2)
        except Exception as exc:
            if getattr(getattr(exc, 'resp', None), 'status', None) == 404:
                account = 'the connected Google account'
                try:
                    user = self.api.about().get(fields='user(emailAddress)').execute(num_retries=1)
                    email = user.get('user', {}).get('emailAddress')
                    if isinstance(email, str) and email:
                        account = email
                except Exception:
                    pass  # Account lookup must not obscure the original folder error.
                raise DriveError(
                    f'Folder {value} is not visible to {account}. '
                    'The folder may be missing or this account may lack access. '
                    'Check access using that account, or reconnect Google Drive with the folder owner account. '
                    'For a link-shared folder, ask the owner to grant that account Editor access directly.'
                ) from None
            raise api_error(exc) from None
        if (info.get('mimeType') != 'application/vnd.google-apps.folder' or info.get('trashed') or
                not info.get('capabilities', {}).get('canAddChildren')):
            raise DriveError('The destination must be an accessible, writable Google Drive folder.')
        return info

    def create_folder(self, name, parent_id=''):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise DriveError('Enter a folder name between 1 and 200 characters.')
        body = {'name': name.strip(), 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id:
            self.validate_folder(parent_id)
            body['parents'] = [folder_id(parent_id)]
        try:
            # Creation is not blindly retried: an ambiguous response must not
            # silently create duplicate folders.
            return self.api.files().create(body=body, fields='id,webViewLink', supportsAllDrives=True).execute(num_retries=0)
        except Exception as exc:
            raise api_error(exc) from None

    def upload_png(self, data, name, destination):
        from googleapiclient.http import MediaIoBaseUpload
        try:
            request = self.api.files().create(
                body={'name': name, 'parents': [folder_id(destination)]},
                media_body=MediaIoBaseUpload(io.BytesIO(data), mimetype='image/png',
                                            chunksize=8 * 1024 * 1024, resumable=True),
                fields='id,webViewLink', supportsAllDrives=True)
            result = None
            while result is None:
                _, result = request.next_chunk(num_retries=2)
            return result
        except DriveError:
            raise
        except Exception as exc:
            raise api_error(exc) from None
