# Authenticated image upload and Buffer publishing

## Goal
Receive a generated image as binary data, commit it to this repository, and publish it with a caption through Buffer to the Share2Me LinkedIn channel.

## Proposed implementation
- Add an authenticated upload endpoint that accepts PNG/JPEG/WebP bytes (or multipart uploads).
- Require a dedicated secret token; compare it using constant-time comparison; never log or return the token.
- Validate MIME type, file signature, max size (for example 8 MiB), and allow only safe filenames.
- Store image at images/<date>-<slug>.<ext> using the GitHub Contents API with base64 file content.
- Return the stable public raw URL only after GitHub commit succeeds.
- Publish via Buffer with assets: [{ image: { url: <raw-image-url>, metadata: { altText: "Share2Me..." } } }].
- Verify Buffer returns a sent status and that the post has at least one image asset.
- Keep GitHub and Buffer credentials in deployment secrets; never put tokens in repository files.
- Add upload and publish failure handling, request size limits, idempotency/deduplication, and audit logs without secrets.

## Important integration limitation
The ChatGPT GitHub connector used in this session has text-file commit operations but no tool to transfer the generated PNG bytes as a binary file. The endpoint requires a caller that can POST the actual image bytes. Merely having GitHub Contents write permission does not make the PNG bytes available to the connector.
