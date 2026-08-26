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
                    "alocacoes_pagamento_fatura, reembolsos_compra, compras, "
                    "execucoes_recorrencia, recorrencias, orcamentos_categoria, "
                    "aportes_reserva, metas_reserva, transferencias, "
                    "auditoria_agente, categorias, cartoes, contas "
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

    def test_request_id_e_propagado_na_resposta(self):
        response = self.client.get("/", headers={"X-Request-ID": "integracao-123"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["X-Request-ID"], "integracao-123")

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

    def test_estorno_de_pagamento_reabre_fatura_e_reverte_saldo_e_limite(self):
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        gasto = self.criar_gasto(
            cartao["id"], valor="125.50", data="2026-07-10T12:00:00"
        )
        pagamento = self.client.post(
            f"/cartoes/{cartao['id']}/pagar_fatura",
            json={"mes_ref": 8, "ano_ref": 2026, "idempotency_key": "pag-estorno-1"},
        )
        self.assertEqual(pagamento.status_code, 200, pagamento.text)

        estorno = self.client.post(
            f"/cartoes/{cartao['id']}/pagamentos/{pagamento.json()['pagamento_id']}/estornar",
            json={"motivo": "Pagamento duplicado", "idempotency_key": "estorno-pag-1"},
        )
        self.assertEqual(estorno.status_code, 200, estorno.text)
        self.assertEqual(Decimal(estorno.json()["novo_saldo"]), Decimal("500.00"))
        self.assertEqual(Decimal(estorno.json()["novo_limite"]), Decimal("874.50"))

        atualizado = self.client.get(f"/gastos_diarios/{gasto['id']}")
        self.assertFalse(atualizado.json()["pago"])
        repetido = self.client.post(
            f"/cartoes/{cartao['id']}/pagamentos/{pagamento.json()['pagamento_id']}/estornar",
            json={"motivo": "Pagamento duplicado", "idempotency_key": "estorno-pag-1"},
        )
        self.assertEqual(repetido.status_code, 200, repetido.text)
        self.assertTrue(repetido.json()["idempotente"])

    def test_edicao_recalcula_fatura_aberta_para_baixo(self):
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        primeiro = self.criar_gasto(cartao["id"], valor="100.00", data="2026-07-10T12:00:00")
        segundo = self.criar_gasto(cartao["id"], valor="100.00", data="2026-07-11T12:00:00")
        parcial = self.client.post(
            f"/cartoes/{cartao['id']}/pagar_fatura",
            json={"valor": "100.00", "mes_ref": 8, "ano_ref": 2026},
        )
        self.assertEqual(parcial.status_code, 200, parcial.text)
        self.assertTrue(self.client.get(f"/gastos_diarios/{primeiro['id']}").json()["pago"])

        editado = self.client.patch(
            f"/gastos_diarios/{segundo['id']}", json={"valor": "50.00"}
        )
        self.assertEqual(editado.status_code, 200, editado.text)
        fatura = self.client.get(
            f"/cartoes/{cartao['id']}/fatura", params={"mes_ref": 8, "ano_ref": 2026}
        )
        self.assertEqual(Decimal(fatura.json()["total"]), Decimal("150.00"))
        self.assertEqual(Decimal(fatura.json()["saldo_restante"]), Decimal("50.00"))

    def test_transferencia_move_saldo_sem_criar_receita_ou_despesa(self):
        origem = self.client.post(
            "/contas/", json={"nome": "Origem", "dono": "Teste", "saldo": "300.00"}
        ).json()
        destino = self.client.post(
            "/contas/", json={"nome": "Destino", "dono": "Teste", "saldo": "50.00"}
        ).json()
        transferencia = self.client.post(
            "/contas/transferencias",
            json={
                "conta_origem_id": origem["id"],
                "conta_destino_id": destino["id"],
                "valor": "75.00",
                "descricao": "Ajuste entre contas",
                "data": "2026-08-20T12:00:00-03:00",
                "idempotency_key": "transf-1",
            },
        )
        self.assertEqual(transferencia.status_code, 200, transferencia.text)
        self.assertEqual(
            Decimal(self.client.get(f"/contas/{origem['id']}").json()["saldo"]),
            Decimal("225.00"),
        )
        self.assertEqual(
            Decimal(self.client.get(f"/contas/{destino['id']}").json()["saldo"]),
            Decimal("125.00"),
        )
        resumo = self.client.get(
            "/relatorios/resumo_mensal", params={"mes": 8, "ano": 2026, "dono": "Teste"}
        ).json()
        self.assertEqual(Decimal(resumo["receitas"]["total"]), Decimal("0"))
        self.assertEqual(Decimal(resumo["despesas"]["total"]), Decimal("0"))

    def test_reembolso_parcial_reduz_parcela_e_restaura_limite(self):
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        gasto = self.criar_gasto(cartao["id"], valor="300.00", parcelas=3)
        resposta = self.client.post(
            f"/compras/{gasto['compra_id']}/reembolsos",
            json={"valor": "50.00", "motivo": "Desconto", "idempotency_key": "reemb-1"},
        )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        cartao_atual = self.client.get(f"/cartoes/{cartao['id']}").json()
        self.assertEqual(Decimal(cartao_atual["limite"]), Decimal("750.00"))
        compra = self.client.get(f"/compras/{gasto['compra_id']}").json()
        self.assertEqual(Decimal(compra["valor_liquido"]), Decimal("250.00"))

    def test_hermes_usa_a_mesma_competencia_padrao_da_api(self):
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        self.criar_gasto(cartao["id"], valor="80.00", data="2026-08-10T12:00:00")
        preview = self.client.post(
            "/agent/v1/pagamentos/fatura/preview",
            headers={"X-Agent-Token": "token-teste"},
            json={"conta_id": cartao["id"]},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["resumo"]["mes_ref"], 9)
        self.assertEqual(preview.json()["resumo"]["ano_ref"], 2026)

    def test_meta_aceita_aporte_e_retirada_sem_apagar_historico(self):
        conta = self.client.post(
            "/contas/", json={"nome": "Reserva", "dono": "Teste", "saldo": "500.00"}
        ).json()
        meta = self.client.post(
            "/planejamento/metas",
            json={"nome": "Emergencia", "dono": "Teste", "valor_alvo": "1000.00"},
        ).json()
        aporte = self.client.post(
            "/aportes_reserva/",
            json={
                "descricao": "Aporte inicial",
                "valor": "200.00",
                "data": "2026-08-20T12:00:00",
                "conta_id": conta["id"],
                "meta_id": meta["id"],
            },
        )
        self.assertEqual(aporte.status_code, 200, aporte.text)
        retirada = self.client.post(
            f"/planejamento/metas/{meta['id']}/retiradas",
            json={
                "conta_id": conta["id"],
                "valor": "50.00",
                "data": "2026-08-21",
                "descricao": "Uso planejado",
            },
        )
        self.assertEqual(retirada.status_code, 200, retirada.text)
        metas = self.client.get("/planejamento/metas", params={"dono": "Teste"}).json()
        self.assertEqual(Decimal(metas[0]["saldo"]), Decimal("150.00"))
        movimentos = self.client.get(
            "/aportes_reserva/", params={"meta_id": meta["id"]}
        ).json()
        self.assertEqual({item["tipo"] for item in movimentos}, {"aporte", "retirada"})

    def test_recorrencia_processa_cada_competencia_uma_unica_vez(self):
        conta = self.client.post(
            "/contas/", json={"nome": "Mensal", "dono": "Teste", "saldo": "500.00"}
        ).json()
        recorrencia = self.client.post(
            "/planejamento/recorrencias",
            json={
                "tipo_lancamento": "gasto",
                "descricao": "Internet",
                "valor": "50.00",
                "dia_mes": 1,
                "proxima_data": "2026-08-01",
                "conta_id": conta["id"],
                "tipo_pagamento": "pix",
                "parcelas": 1,
            },
        )
        self.assertEqual(recorrencia.status_code, 200, recorrencia.text)
        primeira = self.client.post(
            "/planejamento/recorrencias/processar", params={"ate": "2026-08-01"}
        )
        segunda = self.client.post(
            "/planejamento/recorrencias/processar", params={"ate": "2026-08-01"}
        )
        self.assertEqual(primeira.status_code, 200, primeira.text)
        self.assertEqual(primeira.json()["total"], 1)
        self.assertEqual(segunda.json()["total"], 0)
        saldo = self.client.get(f"/contas/{conta['id']}").json()["saldo"]
        self.assertEqual(Decimal(saldo), Decimal("450.00"))

    def test_orcamento_e_projecao_consideram_gastos_e_fatura_aberta(self):
        categoria = self.client.post("/categorias/", json={"nome": "Casa"}).json()
        cartao = self.criar_cartao(saldo="500.00", limite="1000.00")
        gasto = self.client.post(
            "/gastos_diarios/",
            json={
                "descricao": "Moveis",
                "valor": "300.00",
                "data": "2026-08-10T12:00:00",
                "cartao_id": cartao["id"],
                "categoria_id": categoria["id"],
                "tipo_pagamento": "credito",
                "parcelas": 1,
            },
        )
        self.assertEqual(gasto.status_code, 200, gasto.text)
        orcamento = self.client.post(
            "/planejamento/orcamentos",
            json={
                "categoria_id": categoria["id"],
                "dono": "Teste",
                "mes": 8,
                "ano": 2026,
                "limite": "250.00",
                "alerta_percentual": 80,
            },
        )
        self.assertEqual(orcamento.status_code, 200, orcamento.text)
        status = self.client.get(
            "/relatorios/orcamentos/status",
            params={"mes": 8, "ano": 2026, "dono": "Teste"},
        ).json()
        self.assertEqual(status[0]["situacao"], "estourado")
        projecao = self.client.get(
            "/relatorios/projecao", params={"dias": 90, "dono": "Teste"}
        )
        self.assertEqual(projecao.status_code, 200, projecao.text)
        self.assertTrue(any(item["tipo"] == "fatura" for item in projecao.json()["eventos"]))


if __name__ == "__main__":
    unittest.main()
