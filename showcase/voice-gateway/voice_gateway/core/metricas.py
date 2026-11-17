# -*- coding: utf-8 -*-
"""Métricas de latência do pipeline de voz.

Nenhum valor é inventado: todas as amostras vêm de medições reais feitas no
servidor ou informadas pelo cliente (tempo de detecção de barge-in).
"""

from __future__ import annotations

import statistics
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Deque, Dict, List

from ..models import agora_iso

TIPOS = (
    "stt",
    "processamento",
    "tts",
    "interrupcao_deteccao",
    "interrupcao_envio",
    "interrupcao_servidor",
    "interrupcao_tts",
    "interrupcao_som",
    "interrupcao_total",
)


@dataclass
class AmostraLatencia:
    tipo: str
    ms: float
    timestamp: str = field(default_factory=agora_iso)
    sessao_id: str = ""
    tarefa_id: str = ""
    detalhes: Dict[str, Any] = field(default_factory=dict)

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Metricas:
    def __init__(self, maximo: int = 4000) -> None:
        self._amostras: Deque[AmostraLatencia] = deque(maxlen=maximo)
        self._trava = threading.Lock()

    def registrar(
        self,
        tipo: str,
        ms: float,
        sessao_id: str = "",
        tarefa_id: str = "",
        **detalhes: Any,
    ) -> AmostraLatencia:
        amostra = AmostraLatencia(
            tipo=tipo,
            ms=round(float(ms), 2),
            sessao_id=sessao_id,
            tarefa_id=tarefa_id,
            detalhes=detalhes,
        )
        with self._trava:
            self._amostras.append(amostra)
        return amostra

    def listar(self, limite: int = 200, sessao_id: str = "") -> List[Dict[str, Any]]:
        with self._trava:
            dados = list(self._amostras)
        if sessao_id:
            dados = [a for a in dados if a.sessao_id == sessao_id]
        return [a.para_dict() for a in dados[-limite:]]

    def resumo(self, sessao_id: str = "") -> Dict[str, Any]:
        with self._trava:
            dados = list(self._amostras)
        if sessao_id:
            dados = [a for a in dados if a.sessao_id == sessao_id]
        resultado: Dict[str, Any] = {
            "total_amostras": len(dados),
            "por_tipo": {},
        }
        for tipo in TIPOS:
            valores = sorted(a.ms for a in dados if a.tipo == tipo)
            if not valores:
                continue
            resultado["por_tipo"][tipo] = {
                "n": len(valores),
                "min": round(valores[0], 2),
                "p50": round(statistics.median(valores), 2),
                "p95": round(valores[min(len(valores) - 1, int(len(valores) * 0.95))], 2),
                "max": round(valores[-1], 2),
            }
        return resultado
