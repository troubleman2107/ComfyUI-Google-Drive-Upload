"""Upload generated IMAGE tensors to the configured personal Google Drive."""
import io
import json
import re
import numpy as np
from PIL import Image
from ._google_drive_helpers import DriveError
from ._google_drive_service import DriveService
from ._save_helpers import _build_pnginfo, _expand_date_tokens


class GoogleDriveUpload:
    DESCRIPTION = ('Upload PNG images to My Drive. Open Google Drive Setup once to connect your account. '
                   'folder_id is the ID from a Drive folder URL. Every queued run creates new files; '
                   'existing files are never overwritten. Credentials are stored on the server, not in the workflow.')
    CATEGORY = 'Google Drive'
    RETURN_TYPES = ('IMAGE', 'STRING', 'STRING', 'STRING')
    RETURN_NAMES = ('image', 'file_ids', 'file_urls', 'folder_id')
    FUNCTION = 'upload'
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'image': ('IMAGE',),
            'folder_id': ('STRING', {'default': '', 'tooltip': 'ID after /folders/ in the Google Drive URL.'}),
            'filename_prefix': ('STRING', {'default': 'img'}),
            'enabled': ('BOOLEAN', {'default': True}),
        }, 'hidden': {'prompt': 'PROMPT', 'extra_pnginfo': 'EXTRA_PNGINFO'}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float('nan')

    def upload(self, image, folder_id, filename_prefix='img', enabled=True, prompt=None, extra_pnginfo=None):
        completed = []
        if enabled:
            # Validate before encoding images or making any uploads.
            service = DriveService()
            service.validate_folder(folder_id)
            stem = _expand_date_tokens(str(filename_prefix or 'img')).strip()
            stem = re.sub(r'[\x00-\x1f/\\]', '_', stem)
            stem = re.sub(r'(?i)\.png$', '', stem).strip(' .')[:180] or 'img'
            count = len(image)
            for index, tensor in enumerate(image):
                try:
                    array = np.nan_to_num(tensor.cpu().numpy(), nan=0.0, posinf=1.0, neginf=0.0)
                    pil = Image.fromarray((np.clip(array, 0, 1) * 255).astype(np.uint8))
                    buffer = io.BytesIO()
                    pil.save(buffer, format='PNG', pnginfo=_build_pnginfo(prompt=prompt, extra_pnginfo=extra_pnginfo))
                    name = f'{stem}_{index + 1:03}.png' if count > 1 else f'{stem}.png'
                    completed.append(service.upload_png(buffer.getvalue(), name, folder_id))
                except Exception as exc:
                    reason = str(exc) if isinstance(exc, DriveError) else 'Image encoding or upload failed.'
                    done = [{'id': f['id'], 'url': f.get('webViewLink', '')} for f in completed]
                    raise DriveError(f'Image {index + 1}/{count}: {reason} Completed uploads: {json.dumps(done)}. '
                                     'Check Drive before retrying; a new run uploads the whole batch again.') from None
        ids = [f['id'] for f in completed]
        urls = [f.get('webViewLink') or f"https://drive.google.com/file/d/{f['id']}/view" for f in completed]
        return {'ui': {'text': [f'Uploaded {len(ids)} image(s).' if enabled else 'Google Drive upload disabled.']},
                'result': (image, json.dumps(ids), json.dumps(urls), folder_id)}


NODE_CLASS_MAPPINGS = {'GoogleDriveUpload': GoogleDriveUpload}
NODE_DISPLAY_NAME_MAPPINGS = {'GoogleDriveUpload': 'Google Drive Upload'}
