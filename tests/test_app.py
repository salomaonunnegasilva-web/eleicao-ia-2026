import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_db_file = tempfile.NamedTemporaryFile(prefix="eleicao-tests-", suffix=".db", delete=False)
_db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_db_file.name).as_posix()}"
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["MONTE_CARLO_ITERATIONS"] = "100"
os.environ["MONTE_CARLO_SEED"] = "42"
os.environ["ADMIN_ENABLED"] = "true"

from fastapi.testclient import TestClient

from app.api.main import app
from app.rag.answer_generation import LLMProviderError, generate_grounded_answer


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def test_root_exposes_demo_metadata(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data_mode"], "demo_synthetic")
        self.assertIn("synthetic", payload["data_notice"].lower())

    def test_candidate_profile_returns_registry_answer(self):
        response = self.client.post(
            "/api/chat",
            json={"query": "Qual é o partido de Ciro Gomes?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"], "candidate_profile")
        self.assertIn("PDT", payload["answer"])

    def test_poll_registration_question_uses_rag_route(self):
        response = self.client.post(
            "/api/chat",
            json={
                "query": (
                    "Até quantos dias antes da divulgação as pesquisas "
                    "eleitorais devem ser registradas?"
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"], "rag")
        self.assertTrue(payload["sources"])

    def test_unknown_forecast_scenario_returns_404(self):
        response = self.client.get(
            "/api/forecast/simulation",
            params={"scenario": "missing", "iterations": 100},
        )
        self.assertEqual(response.status_code, 404)

    def test_unsupported_upload_returns_400(self):
        response = self.client.post(
            "/api/ingest/file",
            files={"file": ("bad.exe", b"bad", "application/octet-stream")},
            data={"title": "Unsupported"},
        )
        self.assertEqual(response.status_code, 400)

    def test_seed_is_idempotent_for_existing_database(self):
        first = self.client.post("/api/sources/seed")
        second = self.client.post("/api/sources/seed")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

    def test_simulation_is_reproducible(self):
        first = self.client.get(
            "/api/forecast/simulation",
            params={"iterations": 100},
        )
        second = self.client.get(
            "/api/forecast/simulation",
            params={"iterations": 100},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())

    def test_retrieval_evaluation_is_computed(self):
        response = self.client.get("/api/evaluations/retrieval")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["successful"], payload["total"])
        self.assertEqual(payload["score"], 100.0)
        self.assertIn("not a RAGAS evaluation", payload["limitations"])

    def test_provider_failure_falls_back_locally(self):
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "test-key",
                "LLM_MODEL": "gemini-2.5-flash-lite",
            },
        ), patch(
            "app.rag.answer_generation.call_gemini_api",
            side_effect=LLMProviderError("Gemini generation failed."),
        ):
            result = generate_grounded_answer(
                db=None,
                query_text="Pergunta sem contexto",
                context_chunks=[],
            )
        self.assertEqual(result["provider"], "local-fallback")
        self.assertEqual(result["model"], "deterministic-local")
        self.assertEqual(result["fallback_reason"], "Gemini generation failed.")


if __name__ == "__main__":
    unittest.main()
