# -*- coding: utf-8 -*-
"""Ponto de entrada do Voice Gateway.

Uso:
    python -m voice_gateway.run
    python -m voice_gateway.run --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import argparse

import uvicorn

from . import config as config_mod
from .config import carregar_config, obter_token
from .main import criar_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Gateway — CDC e Salomão AI")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--token", default=None, help="Sobrescreve o token de acesso")
    args = parser.parse_args()

    config = carregar_config()
    if config_mod.AVISO_CONFIG_LEGADA:
        print("AVISO: " + config_mod.AVISO_CONFIG_LEGADA)
    if args.host:
        config.servidor.host = args.host
    if args.port:
        config.servidor.port = args.port
    token = args.token or obter_token(config)

    print("Voice Gateway")
    print(f"  Endereço: http://{config.servidor.host}:{config.servidor.port}")
    print(f"  Token: {token}")
    print("  Guarde o token: ele não é exibido novamente pela API.")
    if config.servidor.host not in ("127.0.0.1", "localhost", "::1"):
        print("  AVISO: escutando fora do loopback — use TLS/Tailscale e proteja o token.")

    app = criar_app(config, token)
    uvicorn.run(
        app,
        host=config.servidor.host,
        port=config.servidor.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
