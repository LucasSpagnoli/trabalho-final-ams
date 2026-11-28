"""Integração do fluxo de cadastro, revisão e privacidade; execute python -m unittest discover -s tests."""
import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class APIFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        os.environ["AMS_DATA_DIR"] = cls.directory.name
        os.environ["AMS_ADMIN_KEY"] = "admin-test-only"
        os.environ["AMS_COLLABORATOR_KEY"] = "collab-test-only"
        cls.app_module = importlib.import_module("app")
        cls.client = TestClient(cls.app_module.app)
        cls.admin = {"X-API-Key": "admin-test-only"}
        cls.collab = {"X-API-Key": "collab-test-only", "X-User": "autor"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.directory.cleanup()

    def test_approval_and_media_privacy(self):
        response = self.client.post("/sinais", headers=self.collab, json={"palavra": "AMIGO", "descricao_textual": "Mãos em movimento"})
        self.assertEqual(response.status_code, 201)
        signal_id = response.json()["id"]
        self.assertEqual(self.client.get("/sinais").json(), [])
        self.assertEqual(self.client.get(f"/sinais/{signal_id}").status_code, 404)

        mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
        form = {"regiao": "SC", "consentiu": "true", "termo_versao": "1", "maior_de_18": "true"}
        files = {"video": ("sinal.mp4", mp4, "video/mp4"), "video_exemplo": ("exemplo.mp4", mp4, "video/mp4")}
        variation = self.client.post(f"/sinais/{signal_id}/variacoes", headers=self.collab, data=form, files=files)
        self.assertEqual(variation.status_code, 201, variation.text)
        variation_id = variation.json()["id"]
        self.assertEqual(self.client.get(f"/videos/{variation_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/videos/{variation_id}?tipo=exemplo", headers=self.admin).status_code, 200)

        self.assertEqual(self.client.post(f"/revisao/sinais/{signal_id}", headers=self.collab, json={"decisao": "Aprovado"}).status_code, 403)
        self.assertEqual(self.client.post(f"/revisao/sinais/{signal_id}", headers=self.admin, json={"decisao": "Aprovado"}).status_code, 200)
        self.assertEqual(self.client.post(f"/revisao/variacoes/{variation_id}", headers=self.admin, json={"decisao": "Aprovado"}).status_code, 200)
        self.assertEqual(len(self.client.get("/sinais?q=ami").json()), 1)
        self.assertEqual(self.client.get(f"/videos/{variation_id}?tipo=exemplo").status_code, 200)

        self.assertEqual(self.client.post(f"/variacoes/{variation_id}/revogar-consentimento", headers=self.collab).status_code, 200)
        self.assertEqual(self.client.get(f"/videos/{variation_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/sinais/{signal_id}").json()["variacoes"], [])

    def test_reject_minor_and_invalid_video(self):
        signal_id = self.client.post("/sinais", headers=self.admin, json={"palavra": "CASA", "descricao_textual": "Movimento"}).json()["id"]
        form = {"regiao": "PR", "consentiu": "true", "termo_versao": "1", "maior_de_18": "false"}
        invalid = {"video": ("teste.mp4", b"not a video", "video/mp4")}
        self.assertEqual(self.client.post(f"/sinais/{signal_id}/variacoes", headers=self.collab, data=form, files=invalid).status_code, 422)
        form["maior_de_18"] = "true"
        self.assertEqual(self.client.post(f"/sinais/{signal_id}/variacoes", headers=self.collab, data=form, files=invalid).status_code, 422)
        self.assertEqual(self.client.get(f"/sinais/{signal_id}").json()["variacoes"], [])


if __name__ == "__main__":
    unittest.main()
