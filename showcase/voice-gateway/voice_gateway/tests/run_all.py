# -*- coding: utf-8 -*-
"""Executor único da suíte do Voice Gateway."""

import sys
import unittest


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(
        [
            "voice_gateway.tests.test_router",
            "voice_gateway.tests.test_seguranca",
            "voice_gateway.tests.test_historico",
            "voice_gateway.tests.test_componentes",
            "voice_gateway.tests.test_gateway",
            "voice_gateway.tests.test_api",
            "voice_gateway.tests.test_operacoes",
            "voice_gateway.tests.test_wake",
            "voice_gateway.tests.test_falantes",
            "voice_gateway.tests.test_conversacao",
            "voice_gateway.tests.test_persistencia_contexto",
            "voice_gateway.tests.test_voz",
            "voice_gateway.tests.test_captura",
        ]
    )
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
