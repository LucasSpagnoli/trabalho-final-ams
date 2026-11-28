"""Regras de negócio e persistência, sem servidor ou sockets de rede."""
import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


class DomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        os.environ["AMS_DATA_DIR"] = cls.directory.name
        os.environ["AMS_ADMIN_KEY"] = "admin-test-only"
        os.environ["AMS_COLLABORATOR_KEY"] = "collab-test-only"
        cls.api = importlib.reload(importlib.import_module("app"))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_approval_and_publication(self):
        api = self.api
        signal = api.create_signal(api.Signal(palavra="AMIGO", descricao_textual="Mãos em movimento"), user=("Colaborador", "autor"))
        self.assertEqual(signal["status"], "Submetido")
        self.assertEqual(api.list_signals(ordenar="alfabetica"), [])
        with self.assertRaises(HTTPException) as context:
            api.read_signal(signal["id"])
        self.assertEqual(context.exception.status_code, 404)
        with self.assertRaises(HTTPException) as context:
            api.admin(("Colaborador", "autor"))
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(api.review_signal(signal["id"], api.Decision(decisao="Aprovado"), user=("Administrador", "admin"))["status"], "Aprovado")
        self.assertEqual(len(api.list_signals(q="ami", ordenar="alfabetica")), 1)
        with self.assertRaises(HTTPException) as context:
            api.review_signal(signal["id"], api.Decision(decisao="Recusado"), user=("Administrador", "admin"))
        self.assertEqual(context.exception.status_code, 409)

    def test_revoke_removes_both_videos(self):
        api = self.api
        signal = api.create_signal(api.Signal(palavra="CASA", descricao_textual="Movimento"), user=("Administrador", "admin"))
        first = "sinal-test.mp4"
        second = "exemplo-test.mp4"
        for filename in (first, second):
            (api.MEDIA / filename).write_bytes(b"test")
        with api.connection() as db:
            cur = db.execute("INSERT INTO variacoes(sinal_id,regiao,status,video,video_exemplo,consentimento,autor) VALUES (?,?,?,?,?,?,?)", (signal["id"], "SC", "Aprovado", first, second, '{"versao":"1"}', "autor"))
            variation_id = cur.lastrowid
        with self.assertRaises(HTTPException) as context:
            api.revoke_consent(variation_id, user=("Colaborador", "outro"))
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(api.revoke_consent(variation_id, user=("Colaborador", "autor"))["status"], "Recusado")
        self.assertFalse((api.MEDIA / first).exists())
        self.assertFalse((api.MEDIA / second).exists())
        self.assertEqual(api.read_signal(signal["id"])["variacoes"], [])

    def test_patch_rejects_invalid_fields(self):
        api = self.api
        signal = api.create_signal(api.Signal(palavra="LIVRO", descricao_textual="Movimento"), user=("Administrador", "admin"))
        with self.assertRaises(HTTPException):
            api.update_signal(signal["id"], {"campo_inexistente": "x"}, user=("Administrador", "admin"))
        self.assertEqual(api.update_signal(signal["id"], {"assunto": "Educação"}, user=("Administrador", "admin"))["assunto"], "Educação")


if __name__ == "__main__":
    unittest.main()
