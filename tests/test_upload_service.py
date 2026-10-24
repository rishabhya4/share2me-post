import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from upload_service.app import app


class UploadServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["UPLOAD_STORAGE_DIR"] = self.temp_dir.name
        os.environ["UPLOAD_API_TOKEN"] = "test-token"
        os.environ["MAX_UPLOAD_SIZE_BYTES"] = "16"
        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _auth(self):
        return {"X-Upload-Token": os.environ["UPLOAD_API_TOKEN"]}

    def test_rejects_missing_authentication(self):
        response = self.client.post(
            "/upload",
            files={"file": ("image.jpg", b"\xff\xd8\xff\xdb", "image/jpeg")},
        )
        self.assertEqual(response.status_code, 401)

    def test_rejects_non_image_uploads(self):
        response = self.client.post(
            "/upload",
            headers=self._auth(),
            files={"file": ("note.txt", b"hello world", "text/plain")},
        )
        self.assertEqual(response.status_code, 415)

    def test_rejects_malformed_uploads(self):
        response = self.client.post("/upload", headers=self._auth(), data={"unexpected": "payload"})
        self.assertEqual(response.status_code, 400)

    def test_rejects_oversized_uploads(self):
        oversized = b"\xff\xd8\xff" + (b"a" * 20)
        response = self.client.post(
            "/upload",
            headers=self._auth(),
            files={"file": ("image.jpg", oversized, "image/jpeg")},
        )
        self.assertEqual(response.status_code, 413)

    def test_upload_and_download_succeeds(self):
        image_data = b"\xff\xd8\xff\xdb\x00\x43"
        response = self.client.post(
            "/upload",
            headers=self._auth(),
            files={"file": ("image.jpg", image_data, "image/jpeg")},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("upload_id", body)
        self.assertIn("download_url", body)

        download = self.client.get(f"/upload/{body['upload_id']}", headers=self._auth())
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, image_data)


if __name__ == "__main__":
    unittest.main()
