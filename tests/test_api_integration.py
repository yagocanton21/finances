import os
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text


RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"

if RUN_INTEGRATION_TESTS:
    from fastapi.testclient import TestClient
    from database import engine
    from main import app


@unittest.skipUnless(
    RUN_INTEGRATION_TESTS,
    "Defina RUN_INTEGRATION_TESTS=1 para executar os testes com PostgreSQL",
)
class ApiFinanceiraIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["HERMES_API_TOKEN"] = "token-teste"
        cls.client = TestClient(app)

    def setUp(self):
        # Só é permitido executar este arquivo com RUN_INTEGRATION_TESTS=1.
        # O banco apontado pelo CI é descartável.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE TABLE gasto_diarios, receitas, faturas, "
                    "pagamentos_fatura, "
                    "aportes_reserva, auditoria_agente, categorias, cartoes "
                    "RESTART IDENTITY CASCADE"
                )
            )

    def criar_cartao(self, *, saldo="500.00", limite="1000.00"):
        response = self.client.post(
            "/cartoes/",
            json={
                "nome": "Cartão de integração",
                "dono": "Teste",
                "limite": limite,
                "saldo": saldo,
                "data_fatura": 28,
                "dia_vencimento": 5,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def criar_gasto(self, cartao_id, *, valor="100.00", parcelas=1, data="2026-07-10T12:00:00"):
        response = self.client.post(
            "/gastos_diarios/",
            json={
                "descricao": "Compra de integração",
                "valor": valor,
                "data": data,
                "cartao_id": cartao_id,
                "tipo_pagamento": "credito",
                "parcelas": parcelas,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_compra_parcelada_cria_parcelas_estruturadas(self):
        cartao = self.criar_cartao()
        primeira = self.criar_gasto(cartao["id"], valor="300.00", parcelas=3)

        self.assertEqual(primeira["parcelas"], 3)
        self.assertEqual(primeira["numero_parcela"], 1)
        self.assertTrue(primeira["compra_id"])

        response = self.client.get(
            "/gastos_diarios/",
            params={"compra_id": primeira["compra_id"], "limit": 120},
        )
        self.assertEqual(response.status_code, 200, response.text)
        itens = response.json()["items"]
        self.assertEqual(len(itens), 3)
        self.assertEqual(
            sum((Decimal(item["valor"]) for item in itens), Decimal("0")),
            Decimal("300.00"),
        )
        self.assertEqual(
            sorted(item["numero_parcela"] for item in itens), [1, 2, 3]
        )

    def test_edicao_e_exclusao_de_gasto_nao_pago(self):
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        gasto = self.criar_gasto(cartao["id"], valor="100.00")

        response = self.client.patch(
            f"/gastos_diarios/{gasto['id']}",
            json={"descricao": "Compra editada", "valor": "125.50"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["descricao"], "Compra editada")
        self.assertEqual(Decimal(response.json()["valor"]), Decimal("125.50"))

        response = self.client.delete(f"/gastos_diarios/{gasto['id']}")
        self.assertEqual(response.status_code, 200, response.text)

        response = self.client.get(f"/gastos_diarios/{gasto['id']}")
        self.assertEqual(response.status_code, 404, response.text)

        response = self.client.get(f"/cartoes/{cartao['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(Decimal(response.json()["limite"]), Decimal("1000.00"))

    def test_pagamento_total_debita_saldo_libera_limite_e_fecha_gastos(self):
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        gasto = self.criar_gasto(
            cartao["id"], valor="125.50", data="2026-07-10T12:00:00"
        )

        response = self.client.post(
            f"/cartoes/{cartao['id']}/pagar_fatura",
            json={"mes_ref": 8, "ano_ref": 2026},
        )
        self.assertEqual(response.status_code, 200, response.text)
        corpo = response.json()
        self.assertEqual(Decimal(corpo["valor_pago"]), Decimal("125.50"))
        self.assertEqual(Decimal(corpo["novo_saldo"]), Decimal("374.50"))
        # O limite disponível volta ao valor anterior à compra.
        self.assertEqual(Decimal(corpo["novo_limite"]), Decimal("1000.00"))

        response = self.client.get(f"/gastos_diarios/{gasto['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["pago"])

    def test_pagamento_parcial_debita_e_mantem_gastos_em_aberto(self):
        # Caracteriza o comportamento atual até a implementação de PagamentoFatura:
        # o débito ocorre e os gastos permanecem abertos para o saldo restante.
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        gasto = self.criar_gasto(
            cartao["id"], valor="125.50", data="2026-07-10T12:00:00"
        )

        response = self.client.post(
            f"/cartoes/{cartao['id']}/pagar_fatura",
            json={"valor": "50.00", "mes_ref": 8, "ano_ref": 2026},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(Decimal(response.json()["valor_pago"]), Decimal("50.00"))

        response = self.client.get(f"/gastos_diarios/{gasto['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["pago"])

        segunda = self.client.post(
            f"/cartoes/{cartao['id']}/pagar_fatura",
            json={"valor": "75.50", "mes_ref": 8, "ano_ref": 2026},
        )
        self.assertEqual(segunda.status_code, 200, segunda.text)
        self.assertEqual(Decimal(segunda.json()["saldo_restante"]), Decimal("0.00"))

        excesso = self.client.post(
            f"/cartoes/{cartao['id']}/pagar_fatura",
            json={"mes_ref": 8, "ano_ref": 2026},
        )
        self.assertEqual(excesso.status_code, 409, excesso.text)

    def test_pagamento_idempotente_nao_debita_duas_vezes(self):
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        self.criar_gasto(cartao["id"], valor="125.50", data="2026-07-10T12:00:00")
        payload = {
            "valor": "50.00",
            "mes_ref": 8,
            "ano_ref": 2026,
            "idempotency_key": "pagamento-teste-1",
        }

        primeira = self.client.post(
            f"/cartoes/{cartao['id']}/pagar_fatura", json=payload
        )
        segunda = self.client.post(
            f"/cartoes/{cartao['id']}/pagar_fatura", json=payload
        )
        self.assertEqual(primeira.status_code, 200, primeira.text)
        self.assertEqual(segunda.status_code, 200, segunda.text)
        self.assertEqual(primeira.json()["pagamento_id"], segunda.json()["pagamento_id"])
        self.assertEqual(Decimal(segunda.json()["saldo_restante"]), Decimal("75.50"))

    def test_hermes_reconcilia_fatura_sem_debitar_e_marca_parcela(self):
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        primeira = self.criar_gasto(
            cartao["id"], valor="100.00", parcelas=2, data="2026-07-10T12:00:00"
        )
        headers = {"X-Agent-Token": "token-teste", "Idempotency-Key": "hermes-pag-1"}

        preview = self.client.post(
            "/agent/v1/pagamentos/fatura/preview",
            headers={"X-Agent-Token": "token-teste"},
            json={"conta_id": cartao["id"], "mes_ref": 8, "ano_ref": 2026},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertTrue(preview.json()["precisa_confirmacao"])
        self.assertEqual(Decimal(preview.json()["resumo"]["valor"]), Decimal("50.00"))

        reconciliado = self.client.post(
            "/agent/v1/pagamentos/fatura/reconciliar",
            headers=headers,
            json={
                "conta_id": cartao["id"],
                "mes_ref": 8,
                "ano_ref": 2026,
                "confirmado": True,
            },
        )
        self.assertEqual(reconciliado.status_code, 200, reconciliado.text)
        self.assertFalse(reconciliado.json()["movimentou_saldo"])
        self.assertEqual(Decimal(reconciliado.json()["novo_saldo"]), Decimal("500.00"))
        self.assertEqual(Decimal(reconciliado.json()["novo_limite"]), Decimal("950.00"))

        gasto_atualizado = self.client.get(f"/gastos_diarios/{primeira['id']}")
        self.assertEqual(gasto_atualizado.status_code, 200, gasto_atualizado.text)
        self.assertTrue(gasto_atualizado.json()["pago"])

        repetido = self.client.post(
            "/agent/v1/pagamentos/fatura/reconciliar",
            headers=headers,
            json={
                "conta_id": cartao["id"],
                "mes_ref": 8,
                "ano_ref": 2026,
                "confirmado": True,
            },
        )
        self.assertEqual(repetido.status_code, 200, repetido.text)
        self.assertTrue(repetido.json()["idempotente"])

        cartao_atualizado = self.client.get(f"/cartoes/{cartao['id']}")
        self.assertEqual(cartao_atualizado.status_code, 200, cartao_atualizado.text)
        self.assertEqual(Decimal(cartao_atualizado.json()["saldo"]), Decimal("500.00"))
        self.assertEqual(Decimal(cartao_atualizado.json()["limite"]), Decimal("950.00"))

    def test_operacao_rejeita_limite_insuficiente_sem_criar_gasto(self):
        cartao = self.criar_cartao(saldo="500.00", limite="50.00")
        response = self.client.post(
            "/gastos_diarios/",
            json={
                "descricao": "Compra acima do limite",
                "valor": "50.01",
                "data": datetime(2026, 7, 10, 12, 0).isoformat(),
                "cartao_id": cartao["id"],
                "tipo_pagamento": "credito",
                "parcelas": 1,
            },
        )
        self.assertEqual(response.status_code, 409, response.text)

        response = self.client.get("/gastos_diarios/", params={"limit": 120})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
