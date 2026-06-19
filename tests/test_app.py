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
os.environ["DATA_MODE"] = "official_live"

from fastapi.testclient import TestClient

from app.api.main import SessionLocal, app
from app.data_sources.official_answering import (
    build_integrity_chunks,
    build_legislative_chunks,
)
from app.data_sources.tse_client import parse_calendar_html
from app.rag.answer_generation import LLMProviderError, generate_grounded_answer
from app.rag.retrieval import classify_query, retrieve_hybrid_chunks


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def test_root_exposes_official_live_metadata(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data_mode"], "official_live")
        self.assertIn("official-first", payload["data_notice"].lower())

    @patch(
        "app.data_sources.official_answering.build_calendar_chunks",
        return_value=[],
    )
    def test_policy_question_refuses_synthetic_substitution(self, _calendar):
        response = self.client.post(
            "/api/chat",
            json={"query": "Quais propostas de Lula e Flávio para 2026?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"], "official_policy")
        self.assertIn("não foram usados", payload["answer"])
        self.assertEqual(payload["provider"], "official-evidence-gate")

    @patch("app.api.routes_chat.build_calendar_chunks")
    def test_poll_registration_question_uses_official_calendar_route(
        self,
        calendar_chunks,
    ):
        calendar_chunks.return_value = [
            {
                "document_id": "tse-calendar-test",
                "text": (
                    "1º DE JANEIRO: pesquisas devem ser registradas no PesqEle "
                    "até cinco dias antes da divulgação."
                ),
                "score": 1.0,
                "title": "Calendário Eleitoral 2026 - 1º de janeiro",
                "source_type": "official_tse_calendar",
                "source_url": "https://www.tse.jus.br/",
                "author": "Tribunal Superior Eleitoral",
                "publication_date": None,
                "official": True,
                "live_data": True,
                "retrieved_at": "2026-06-15T00:00:00+00:00",
            }
        ]
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
        self.assertEqual(payload["route"], "official_calendar")
        self.assertTrue(payload["sources"][0]["official"])
        self.assertTrue(payload["sources"][0]["live_data"])

    @patch("app.api.routes_chat.build_legislative_chunks")
    def test_legislative_question_uses_official_adapter(
        self,
        legislative_chunks,
    ):
        legislative_chunks.return_value = [
            {
                "document_id": "deputy-1-expenses",
                "text": "A API oficial registra R$ 100,00 em despesas.",
                "score": 1.0,
                "title": "Despesas oficiais - Pessoa Teste",
                "source_type": "official_deputy_expenses",
                "source_url": "https://dadosabertos.camara.leg.br/",
                "author": "Câmara dos Deputados - Dados Abertos",
                "publication_date": "2026-06-15",
                "official": True,
                "live_data": True,
                "retrieved_at": "2026-06-15T00:00:00+00:00",
            }
        ]
        response = self.client.post(
            "/api/chat",
            json={"query": "Quais os gastos da deputada Pessoa Teste?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"], "official_legislative")
        self.assertIn("fontes oficiais", payload["answer"])
        self.assertTrue(payload["sources"][0]["official"])

    @patch("app.data_sources.official_answering.fetch_senator_recent_processes")
    @patch("app.data_sources.official_answering.resolve_current_officeholders")
    def test_generic_projects_query_fetches_senate_processes(
        self,
        officeholders,
        recent_processes,
    ):
        officeholders.return_value = [
            {
                "id": 5894,
                "name": "Flávio Bolsonaro",
                "party": "PL",
                "state": "RJ",
                "profile_url": "https://www25.senado.leg.br/perfil/5894",
                "source": "Senado Federal - Dados Abertos",
                "source_url": "https://www12.senado.leg.br/dados-abertos",
                "office": "senator",
            }
        ]
        recent_processes.return_value = [
            {
                "id": 1,
                "identifier": "PL 1/2026",
                "summary": "Projeto demonstrativo retornado pela API oficial.",
                "presented_at": "2026-01-10",
                "status": "Em tramitação",
                "document_url": "https://legis.senado.leg.br/processo/1",
            }
        ]

        chunks = build_legislative_chunks(
            "Quais projetos recentes estão associados ao senador Flávio Bolsonaro?"
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[1]["source_type"], "official_senator_process")
        recent_processes.assert_called_once_with(5894, limit=5)

    def test_integrity_keywords_route_to_official_integrity(self):
        self.assertEqual(
            classify_query(
                "Ha processos judiciais contra a deputada Tabata Amaral?"
            ),
            "official_integrity",
        )
        self.assertEqual(
            classify_query(
                "Qual remuneracao aparece no Portal da Transparencia?"
            ),
            "official_integrity",
        )

    @patch("app.data_sources.official_answering.fetch_process_by_number")
    def test_process_number_query_builds_datajud_chunks(self, fetch_process):
        fetch_process.return_value = [
            {
                "numeroProcesso": "00008323520184013202",
                "tribunal": "TRF1",
                "_datajud_index": "api_publica_trf1",
                "classe": {"nome": "Procedimento do Juizado Especial Civel"},
                "dataAjuizamento": "2018-10-29T00:00:00.000Z",
                "grau": "JE",
                "nivelSigilo": 0,
                "orgaoJulgador": {"nome": "JEF Adj - Tefe"},
                "assuntos": [{"nome": "Concessao"}],
                "movimentos": [
                    {
                        "nome": "Distribuicao",
                        "dataHora": "2018-10-30T14:06:24.000Z",
                    }
                ],
            }
        ]

        chunks = build_integrity_chunks(
            "Consulte o processo 0000832-35.2018.4.01.3202"
        )

        self.assertEqual(chunks[0]["source_type"], "official_datajud_process")
        self.assertIn("nao implica culpa", chunks[0]["text"])

    @patch("app.api.routes_chat.build_integrity_chunks", return_value=[])
    def test_name_only_judicial_query_refuses_broad_search(self, _chunks):
        response = self.client.post(
            "/api/chat",
            json={
                "query": (
                    "Quais processos judiciais existem contra a deputada "
                    "Tabata Amaral?"
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"], "official_integrity")
        self.assertEqual(payload["provider"], "official-evidence-gate")
        self.assertIn("nao faz busca ampla por nome", payload["answer"])

    @patch("app.data_sources.official_answering.resolve_current_officeholders")
    def test_salary_question_returns_transparency_scope_guardrail(
        self,
        officeholders,
    ):
        officeholders.return_value = [
            {
                "id": 204534,
                "name": "Tabata Amaral",
                "party": "PSB",
                "state": "SP",
                "profile_url": "https://dadosabertos.camara.leg.br/",
                "source": "Camara dos Deputados - Dados Abertos",
                "source_url": "https://dadosabertos.camara.leg.br/",
                "office": "deputy",
            }
        ]

        chunks = build_integrity_chunks(
            "Qual o salario da deputada Tabata Amaral?"
        )

        self.assertEqual(chunks[0]["source_type"], "official_transparency_scope")
        self.assertIn("Remuneracao nominal", chunks[0]["text"])

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

    def test_retrieval_rejects_unrelated_demo_chunks(self):
        db = SessionLocal()
        try:
            chunks = retrieve_hybrid_chunks(
                db,
                "Flávio Bolsonaro",
                limit=4,
                source_types=("demo_policy_scenario",),
            )
        finally:
            db.close()
        self.assertEqual(chunks, [])

    def test_tse_calendar_parser_is_scoped_to_requested_year(self):
        html = """
        <div class="panel__linha">
          <div class="panel__content panel__content-intro">
            <div class="panel__rich-text panel__intro"><h2>2026</h2></div>
          </div>
          <div class="accordion accordion__theme-transparente">
            <div class="accordion__card">
              <h2 class="accordion__card-title">Outubro</h2>
              <div class="accordion__card-body">
                <p><strong>4 DE OUTUBRO - DOMINGO</strong></p>
                <p>Data em que será realizado o primeiro turno.</p>
              </div>
            </div>
          </div>
        </div>
        """
        entries = parse_calendar_html(html, year=2026)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["month"], "Outubro")
        self.assertIn("primeiro turno", entries[0]["text"])

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
