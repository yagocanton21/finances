import json
import logging
import os
import unittest


os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

from app_logging import JsonFormatter, normalize_request_id, request_id_context


class ObservabilityTest(unittest.TestCase):
    def test_json_log_inclui_contexto_da_requisicao(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="financas.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Operacao concluida",
            args=(),
            exc_info=None,
        )
        record.event = "test_event"
        record.status_code = 200
        token = request_id_context.set("request-test-123")
        try:
            payload = json.loads(formatter.format(record))
        finally:
            request_id_context.reset(token)

        self.assertEqual(payload["request_id"], "request-test-123")
        self.assertEqual(payload["event"], "test_event")
        self.assertEqual(payload["status_code"], 200)
        self.assertEqual(payload["message"], "Operacao concluida")

    def test_preserva_request_id_valido(self):
        self.assertEqual(normalize_request_id("cliente-123"), "cliente-123")

    def test_substitui_request_id_invalido(self):
        request_id = normalize_request_id("invalido com espaco")
        self.assertNotEqual(request_id, "invalido com espaco")
        self.assertEqual(len(request_id), 32)


if __name__ == "__main__":
    unittest.main()
