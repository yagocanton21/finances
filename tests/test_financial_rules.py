import os
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

from routers.cartoes import _calcular_fatura_do_mes, _pertence_a_fatura
from routers.gastos_diarios import _aplicar_gasto, _centavos
from schemas.gastos_diarios import ConciliarPagamentoIn, GastoDiarioBase, GastoDiarioPatch, TipoPagamento
from schemas.cartoes import PagarFaturaIn
from schemas.agente import LancamentoAgenteIn
from routers.agente import _mesma_requisicao, _normalizar_requisicao
from services.faturas import _aplicar_pagamento_cartao
from fastapi import HTTPException


class RegrasFinanceirasTest(unittest.TestCase):
    def test_reconciliacao_restaura_limite_sem_movimentar_saldo(self):
        cartao = SimpleNamespace(
            saldo=Decimal("500.00"), limite=Decimal("900.00")
        )

        _aplicar_pagamento_cartao(
            cartao,
            Decimal("50.00"),
            movimentar_saldo=False,
            restaurar_limite=True,
        )

        self.assertEqual(cartao.saldo, Decimal("500.00"))
        self.assertEqual(cartao.limite, Decimal("950.00"))

    def test_compra_apos_fechamento_vai_para_mes_seguinte(self):
        gasto = SimpleNamespace(
            data=datetime(2026, 7, 16), valor=Decimal("100.00")
        )

        self.assertFalse(_pertence_a_fatura(gasto, 15, 8, 2026))
        self.assertTrue(_pertence_a_fatura(gasto, 15, 9, 2026))

    def test_fechamento_de_dezembro_avanca_o_ano(self):
        gasto = SimpleNamespace(
            data=datetime(2026, 12, 20), valor=Decimal("50.00")
        )

        self.assertFalse(_pertence_a_fatura(gasto, 15, 1, 2027))
        self.assertTrue(_pertence_a_fatura(gasto, 15, 2, 2027))

    def test_soma_da_fatura_preserva_centavos(self):
        gastos = [
            SimpleNamespace(
                data=datetime(2026, 7, 1), valor=Decimal("0.10")
            ),
            SimpleNamespace(
                data=datetime(2026, 7, 2), valor=Decimal("0.20")
            ),
        ]

        self.assertEqual(
            _calcular_fatura_do_mes(gastos, 15, 8, 2026),
            Decimal("0.30"),
        )

    def test_arredondamento_de_parcela_e_decimal(self):
        self.assertEqual(_centavos(Decimal("10") / 3), Decimal("3.33"))

    def test_credito_sem_limite_e_bloqueado(self):
        cartao = SimpleNamespace(
            saldo=Decimal("100.00"), limite=Decimal("10.00")
        )

        with self.assertRaises(HTTPException) as erro:
            _aplicar_gasto(
                cartao, TipoPagamento.credito, Decimal("20.00")
            )
        self.assertEqual(erro.exception.status_code, 409)

    def test_debito_sem_saldo_e_bloqueado(self):
        cartao = SimpleNamespace(
            saldo=Decimal("10.00"), limite=Decimal("100.00")
        )

        with self.assertRaises(HTTPException) as erro:
            _aplicar_gasto(cartao, TipoPagamento.pix, Decimal("20.00"))
        self.assertEqual(erro.exception.status_code, 409)

    def test_parcelamento_nao_e_aceito_em_pix(self):
        with self.assertRaises(ValidationError):
            GastoDiarioBase(
                descricao="Compra",
                valor="10.00",
                data=datetime(2026, 7, 30),
                cartao_id=1,
                tipo_pagamento="pix",
                parcelas=2,
            )

    def test_cliente_nao_pode_marcar_gasto_como_pago(self):
        gasto = GastoDiarioBase(
            descricao="Compra",
            valor="10.00",
            data=datetime(2026, 7, 30),
            cartao_id=1,
            tipo_pagamento="credito",
            parcelas=1,
            pago=True,
        )
        self.assertFalse(hasattr(gasto, "pago"))


class CutoffFaturaTest(unittest.TestCase):
    """Testa o fix 1: >= no cutoff (compra no dia do fechamento vai para fatura seguinte)."""

    def test_compra_no_dia_do_fechamento_cai_na_fatura_seguinte(self):
        """Compra no dia 28 com fechamento 28 => fatura do mês seguinte."""
        gasto = SimpleNamespace(
            data=datetime(2026, 7, 28), valor=Decimal("200.00")
        )
        # Com >=, dia 28 (fechamento=28) vai para agosto
        self.assertFalse(_pertence_a_fatura(gasto, 28, 8, 2026))
        self.assertTrue(_pertence_a_fatura(gasto, 28, 9, 2026))

    def test_compra_antes_do_fechamento_fica_no_mes(self):
        """Compra no dia 27 com fechamento 28 => fatura do mês atual."""
        gasto = SimpleNamespace(
            data=datetime(2026, 7, 27), valor=Decimal("100.00")
        )
        self.assertFalse(_pertence_a_fatura(gasto, 28, 7, 2026))
        self.assertTrue(_pertence_a_fatura(gasto, 28, 8, 2026))

    def test_compra_no_dia_1_com_fechamento_15(self):
        """Compra no dia 1 com fechamento 15 => fatura do mês atual."""
        gasto = SimpleNamespace(
            data=datetime(2026, 8, 1), valor=Decimal("50.00")
        )
        self.assertTrue(_pertence_a_fatura(gasto, 15, 9, 2026))

    def test_compra_no_dia_15_com_fechamento_15(self):
        """Compra no dia 15 com fechamento 15 => fatura do mês seguinte (>=)."""
        gasto = SimpleNamespace(
            data=datetime(2026, 8, 15), valor=Decimal("75.00")
        )
        self.assertFalse(_pertence_a_fatura(gasto, 15, 9, 2026))
        self.assertTrue(_pertence_a_fatura(gasto, 15, 10, 2026))

    def test_fechamento_28_dezembro_avanca_para_janeiro(self):
        """Compra dia 28/12 com fechamento 28 => fatura janeiro do ano seguinte."""
        gasto = SimpleNamespace(
            data=datetime(2026, 12, 28), valor=Decimal("300.00")
        )
        self.assertFalse(_pertence_a_fatura(gasto, 28, 1, 2027))
        self.assertTrue(_pertence_a_fatura(gasto, 28, 2, 2027))

    def test_calculo_fatura_com_gastos_mistos(self):
        """Gastos antes e no dia do fechamento devem ser separados corretamente."""
        gastos = [
            SimpleNamespace(data=datetime(2026, 7, 27), valor=Decimal("100.00")),  # julho
            SimpleNamespace(data=datetime(2026, 7, 28), valor=Decimal("200.00")),  # agosto (>=)
            SimpleNamespace(data=datetime(2026, 7, 29), valor=Decimal("50.00")),   # agosto
        ]
        # Fatura de julho: só o gasto do dia 27
        self.assertEqual(
            _calcular_fatura_do_mes(gastos, 28, 8, 2026),
            Decimal("100.00"),
        )
        # Fatura de agosto: gastos do dia 28 e 29
        self.assertEqual(
            _calcular_fatura_do_mes(gastos, 28, 9, 2026),
            Decimal("250.00"),
        )


class PagarFaturaSchemaTest(unittest.TestCase):
    """Testa o fix 2: schema PagarFaturaIn."""

    def test_schema_aceita_vazio(self):
        """Chamada sem parâmetros deve funcionar (retrocompatível)."""
        pag = PagarFaturaIn()
        self.assertIsNone(pag.valor)
        self.assertIsNone(pag.mes_ref)
        self.assertIsNone(pag.ano_ref)

    def test_schema_aceita_todos_campos(self):
        pag = PagarFaturaIn(
            valor=Decimal("150.00"), mes_ref=6, ano_ref=2026
        )
        self.assertEqual(pag.valor, Decimal("150.00"))
        self.assertEqual(pag.mes_ref, 6)
        self.assertEqual(pag.ano_ref, 2026)

    def test_schema_rejeita_valor_zero(self):
        with self.assertRaises(ValidationError):
            PagarFaturaIn(valor=Decimal("0"))

    def test_schema_rejeita_valor_negativo(self):
        with self.assertRaises(ValidationError):
            PagarFaturaIn(valor=Decimal("-10.00"))

    def test_schema_rejeita_mes_invalido(self):
        with self.assertRaises(ValidationError):
            PagarFaturaIn(mes_ref=13)

    def test_schema_aceita_apenas_mes_ref(self):
        """Pode informar só o mês sem o ano."""
        pag = PagarFaturaIn(mes_ref=7)
        self.assertEqual(pag.mes_ref, 7)
        self.assertIsNone(pag.ano_ref)
        self.assertIsNone(pag.valor)


class GastoDiarioPatchSchemaTest(unittest.TestCase):
    """Testa o fix 3: schema GastoDiarioPatch."""

    def test_patch_aceita_vazio(self):
        patch = GastoDiarioPatch()
        self.assertIsNone(patch.descricao)
        self.assertIsNone(patch.valor)
        self.assertIsNone(patch.data)
        self.assertIsNone(patch.categoria_id)

    def test_patch_aceita_apenas_valor(self):
        patch = GastoDiarioPatch(valor=Decimal("99.99"))
        self.assertEqual(patch.valor, Decimal("99.99"))
        self.assertIsNone(patch.descricao)

    def test_patch_aceita_apenas_descricao(self):
        patch = GastoDiarioPatch(descricao="Nova descricao")
        self.assertEqual(patch.descricao, "Nova descricao")
        self.assertIsNone(patch.valor)

    def test_patch_aceita_apenas_data(self):
        data = datetime(2026, 8, 15)
        patch = GastoDiarioPatch(data=data)
        self.assertEqual(patch.data, data)

    def test_patch_aceita_todos_campos(self):
        patch = GastoDiarioPatch(
            descricao="Editado",
            valor=Decimal("50.00"),
            data=datetime(2026, 9, 1),
            categoria_id=3,
        )
        self.assertEqual(patch.descricao, "Editado")
        self.assertEqual(patch.valor, Decimal("50.00"))
        self.assertEqual(patch.categoria_id, 3)

    def test_patch_rejeita_valor_zero(self):
        with self.assertRaises(ValidationError):
            GastoDiarioPatch(valor=Decimal("0"))

    def test_patch_rejeita_descricao_vazia(self):
        with self.assertRaises(ValidationError):
            GastoDiarioPatch(descricao="")

    def test_patch_nao_aceita_cartao_id(self):
        """GastoDiarioPatch não tem campo cartao_id — não deve alterar cartão."""
        patch = GastoDiarioPatch(cartao_id=5)
        self.assertFalse(hasattr(patch, "cartao_id") and patch.cartao_id == 5)

    def test_patch_nao_aceita_parcelas(self):
        """GastoDiarioPatch não tem campo parcelas — não deve alterar parcelas."""
        patch = GastoDiarioPatch(parcelas=3)
        self.assertFalse(hasattr(patch, "parcelas"))

    def test_conciliacao_exige_status_booleano(self):
        self.assertTrue(ConciliarPagamentoIn(pago=True).pago)
        with self.assertRaises(ValidationError):
            ConciliarPagamentoIn()


class LancamentoAgenteSchemaTest(unittest.TestCase):
    def test_gasto_exige_forma_de_pagamento(self):
        with self.assertRaises(ValidationError):
            LancamentoAgenteIn(
                tipo_lancamento="gasto",
                descricao="Mercado",
                valor="10.00",
                data=datetime(2026, 8, 5),
                conta_id=1,
            )

    def test_exige_uma_unica_forma_de_identificar_conta(self):
        with self.assertRaises(ValidationError):
            LancamentoAgenteIn(
                tipo_lancamento="receita",
                descricao="Salario",
                valor="100.00",
                data=datetime(2026, 8, 5),
                conta_id=1,
                conta="Nubank",
            )

    def test_aceita_compra_parcelada_estruturada(self):
        entrada = LancamentoAgenteIn(
            tipo_lancamento="gasto",
            descricao="Geladeira",
            valor="2400.00",
            data=datetime(2026, 8, 5),
            conta="Nubank",
            tipo_pagamento="credito",
            parcelas=12,
            external_id="mensagem-123",
        )
        self.assertEqual(entrada.parcelas, 12)
        self.assertEqual(entrada.external_id, "mensagem-123")

    def test_idempotencia_aceita_o_mesmo_lancamento(self):
        entrada = LancamentoAgenteIn(
            tipo_lancamento="receita",
            descricao="Salario",
            valor="100.00",
            data=datetime(2026, 8, 5),
            conta_id=1,
            external_id="mensagem-123",
        )
        self.assertTrue(_mesma_requisicao(_normalizar_requisicao(entrada), entrada))

    def test_idempotencia_rejeita_lancamento_diferente(self):
        original = LancamentoAgenteIn(
            tipo_lancamento="receita",
            descricao="Salario",
            valor="100.00",
            data=datetime(2026, 8, 5),
            conta_id=1,
        )
        alterado = original.model_copy(update={"valor": Decimal("200.00")})
        self.assertFalse(_mesma_requisicao(_normalizar_requisicao(original), alterado))


if __name__ == "__main__":
    unittest.main()
