# share2me-post

This repository supports uploading an image to an **external HTTP upload service** and then publishing that image to Buffer via GitHub Actions.

## Architecture boundary

- **Upload endpoint (`upload_service/app.py`)**: receives image files over HTTP from external clients.
- **GitHub Actions workflow (`.github/workflows/publish-uploaded-image.yml`)**: triggered *after* upload using an `upload_id` and post text.

GitHub Actions is **not** the upload endpoint. Clients must upload to the external HTTP service first.

## Upload endpoint

### Deploy prerequisites

Deploy `upload_service/app.py` using an ASGI server (for example `uvicorn`) behind HTTPS.
The service must have persistent storage mounted at `UPLOAD_STORAGE_DIR` so uploaded files are available when the workflow later downloads them.

Example local start command:

```bash
pip install -r upload_service/requirements.txt
UPLOAD_API_TOKEN='replace-me' \
UPLOAD_STORAGE_DIR='/var/lib/share2me-post/uploads' \
MAX_UPLOAD_SIZE_BYTES='5242880' \
uvicorn upload_service.app:app --host 0.0.0.0 --port 8000
```

### Required upload service environment variables

- `UPLOAD_API_TOKEN`: bearer token required for upload and download calls.
- `UPLOAD_STORAGE_DIR`: persistent directory where uploaded files are saved.
- `MAX_UPLOAD_SIZE_BYTES`: max request file size (default `5242880`, about 5 MB).

### Example upload request

```bash
curl -X POST "https://upload.example.com/upload" \
  -H "X-Upload-Token: <UPLOAD_API_TOKEN>" \
  -F "file=@/absolute/path/to/image.jpg"
```

Successful response (201):

```json
{
  "upload_id": "<sha256>.<ext>",
  "size": 12345,
  "sha256": "<sha256>",
  "download_url": "https://upload.example.com/upload/<sha256>.<ext>"
}
```

Common failures:

- `401`: missing/invalid token
- `400`: malformed request or invalid upload identifier
- `413`: file too large
- `415`: unsupported/invalid image content

## GitHub Actions publishing workflow

Workflow file: `.github/workflows/publish-uploaded-image.yml`

### Required repository secrets

- `UPLOAD_ENDPOINT_BASE_URL` (for example `https://upload.example.com`)
- `UPLOAD_ENDPOINT_TOKEN` (token to download uploads)
- `BUFFER_ACCESS_TOKEN`
- `BUFFER_PROFILE_ID`

### Trigger options

#### 1) Manual (`workflow_dispatch`)

Inputs:

- `upload_id`: `<sha256>.<ext>` returned from upload endpoint
- `post_text`: text to publish

#### 2) API (`repository_dispatch`)

```bash
gh api repos/rishabhya4/share2me-post/dispatches \
  -f event_type='publish_uploaded_image' \
  -f client_payload='{"upload_id":"<sha256>.<ext>","post_text":"Your caption"}'
```

### Publishing behavior and safety

- Workflow only accepts upload IDs matching `^[a-f0-9]{64}\.(png|jpg|gif|webp)$`.
- Uploaded file is downloaded from the upload service and committed to `images/uploaded/<upload_id>`.
- Deterministic pathing prevents publishing arbitrary repository paths.
- Concurrency group is based on `upload_id`, so duplicate runs for the same image serialize.
- Missing secrets fail early with actionable errors.
- Buffer publish call uses `https://api.bufferapp.com/1/updates/create.json` and repository secrets; credentials are never hard-coded.

## Retention and cleanup notes

Uploaded files are kept in `UPLOAD_STORAGE_DIR` until removed by the operator.
Configure cleanup/retention on the upload service host (for example a scheduled delete policy) according to your operational requirements.
