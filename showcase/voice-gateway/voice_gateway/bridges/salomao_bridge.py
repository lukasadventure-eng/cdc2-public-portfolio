# -*- coding: utf-8 -*-
"""Ponte RPC (JSON Lines via stdin/stdout) para o Salomão AI real.

Executada com o Python do venv de ``D:\\Salomão_IA``. O gateway se comunica
somente com ``ServicoSalomao`` — identidade, memória, sessões, retenção e
políticas do agente continuam pertencendo ao próprio Salomão AI.

Comandos (uma linha JSON por vez):
  {"cmd":"ping"}
  {"cmd":"responder","texto":"...","id":"..."}
  {"cmd":"cancelar","id":"..."}
  {"cmd":"encerrar"}
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import traceback
from pathlib import Path


def _emitir(objeto: dict) -> None:
    sys.stdout.write(json.dumps(objeto, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class Ponte:
    def __init__(self, raiz: str) -> None:
        self.raiz = Path(raiz)
        self.servico = None
        self.fila: queue.Queue = queue.Queue()
        self.cancelamento = threading.Event()
        self.turno_ativo = ""
        self._carregar()

    def _carregar(self) -> None:
        for subpasta in ("Nucleo", "Memoria"):
            caminho = str(self.raiz / subpasta)
            if caminho not in sys.path:
                sys.path.insert(0, caminho)
        os.chdir(str(self.raiz))
        from servicos import ServicoSalomao  # type: ignore

        self.servico = ServicoSalomao()
        self.servico.iniciar()

    def responder(self, comando: dict) -> None:
        turno = str(comando.get("id", ""))
        texto = str(comando.get("texto", "")).strip()
        self.turno_ativo = turno
        self.cancelamento.clear()
        if not texto:
            _emitir({"tipo": "erro", "id": turno, "mensagem": "Mensagem vazia."})
            return
        try:
            cancelavel = lambda: self.cancelamento.is_set()
            ao_token = lambda token: _emitir(
                {"tipo": "token", "id": turno, "texto": str(token)}
            )
            try:
                resultado = self.servico.enviar_mensagem_stream(
                    texto, ao_token=ao_token, cancelavel=cancelavel
                )
            except Exception:  # noqa: BLE001 — versões sem streaming
                if cancelavel():
                    _emitir({"tipo": "cancelado", "id": turno})
                    return
                resultado = self.servico.enviar_mensagem(texto, cancelavel=cancelavel)
            if cancelavel():
                _emitir({"tipo": "cancelado", "id": turno})
                return
            _emitir(
                {
                    "tipo": "fim",
                    "id": turno,
                    "resposta": resultado.get("resposta", ""),
                    "modelo": resultado.get("modelo", ""),
                    "sessao": resultado.get("sessao_id", ""),
                }
            )
        except Exception as erro:  # noqa: BLE001
            _emitir(
                {
                    "tipo": "erro",
                    "id": turno,
                    "mensagem": f"{type(erro).__name__}: {str(erro)[:200]}",
                    "trace": traceback.format_exc(limit=2)[:500],
                }
            )
        finally:
            self.turno_ativo = ""

    def processar(self) -> None:
        while True:
            comando = self.fila.get()
            if comando is None:
                return
            acao = comando.get("cmd")
            if acao == "ping":
                _emitir({"tipo": "pong", "status": "ativo"})
            elif acao == "responder":
                self.responder(comando)
            elif acao == "cancelar":
                if comando.get("id") == self.turno_ativo:
                    self.cancelamento.set()
            elif acao == "registrar":
                # Registra a fala do usuário no histórico nativo SEM gerar resposta.
                try:
                    self.servico._garantir_controlador().adicionar_mensagem(
                        remetente="usuario", conteudo=str(comando.get("texto", ""))
                    )
                    _emitir({"tipo": "registrado", "id": comando.get("id", "")})
                except Exception as erro:  # noqa: BLE001
                    _emitir({
                        "tipo": "erro",
                        "id": comando.get("id", ""),
                        "mensagem": f"Falha ao registrar contexto: {erro}"[:200],
                    })
            elif acao == "feedback":
                # Fala de confirmação com a identidade do Salomão, sem poluir
                # o histórico de conversa com mensagens operacionais internas.
                try:
                    prompt = self.servico._montar_prompt([
                        {"remetente": "usuario", "conteudo": str(comando.get("texto", ""))}
                    ])
                    gerado = self.servico._garantir_modelos().gerar(prompt)
                    _emitir({
                        "tipo": "feedback",
                        "id": comando.get("id", ""),
                        "texto": gerado.get("resposta", ""),
                    })
                except Exception as erro:  # noqa: BLE001
                    _emitir({
                        "tipo": "erro",
                        "id": comando.get("id", ""),
                        "mensagem": f"Falha no feedback: {erro}"[:200],
                    })
            elif acao == "encerrar":
                try:
                    self.servico.encerrar()
                except Exception:  # noqa: BLE001
                    pass
                return


def _ler_stdin(fila: queue.Queue) -> None:
    for linha in sys.stdin:
        try:
            fila.put(json.loads(linha))
        except json.JSONDecodeError:
            fila.put({"cmd": "erro", "mensagem": "JSON inválido"})
    fila.put(None)


def main() -> int:
    if len(sys.argv) < 2:
        _emitir({"tipo": "erro", "mensagem": "Raiz do Salomão AI não informada."})
        return 2
    try:
        ponte = Ponte(sys.argv[1])
    except Exception as erro:  # noqa: BLE001
        _emitir(
            {
                "tipo": "erro",
                "mensagem": f"Falha ao carregar Salomão AI: {type(erro).__name__}: {erro}",
            }
        )
        return 1
    threading.Thread(target=_ler_stdin, args=(ponte.fila,), daemon=True).start()
    try:
        ponte.processar()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
