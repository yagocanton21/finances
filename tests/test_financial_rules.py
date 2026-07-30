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
from schemas.gastos_diarios import GastoDiarioBase, TipoPagamento
from fastapi import HTTPException


class RegrasFinanceirasTest(unittest.TestCase):
    def test_compra_apos_fechamento_vai_para_mes_seguinte(self):
        gasto = SimpleNamespace(
            data=datetime(2026, 7, 16), valor=Decimal("100.00")
        )

        self.assertFalse(_pertence_a_fatura(gasto, 15, 7, 2026))
        self.assertTrue(_pertence_a_fatura(gasto, 15, 8, 2026))

    def test_fechamento_de_dezembro_avanca_o_ano(self):
        gasto = SimpleNamespace(
            data=datetime(2026, 12, 20), valor=Decimal("50.00")
        )

        self.assertTrue(_pertence_a_fatura(gasto, 15, 1, 2027))

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
            _calcular_fatura_do_mes(gastos, 15, 7, 2026),
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


if __name__ == "__main__":
    unittest.main()
