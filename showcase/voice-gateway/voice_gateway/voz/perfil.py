# -*- coding: utf-8 -*-
"""Registro de voz personalizada com consentimento do titular.

Nenhuma amostra é criada, inferida ou presumida autorizada pelo sistema.
O registro só aceita áudio fornecido explicitamente com confirmação de
consentimento. O arquivo fica em ``data/vozes/`` (fora do Git).
"""

from __future__ import annotations

import json
import os
import wave
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List

from ..models import agora_iso, novo_id

CONSENTIMENTO_FRASE = "AUTORIZO_USO_DA_MINHA_VOZ"


@dataclass
class PerfilVoz:
    id: str
    nome: str
    agente_id: str
    idioma: str
    criado_em: str
    arquivo: str
    consentimento: str
    ativo: bool = False

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RegistroVoz:
    def __init__(self, diretorio: Path) -> None:
        self.diretorio = Path(diretorio)
        self.diretorio.mkdir(parents=True, exist_ok=True)
        self.caminho_indice = self.diretorio / "indice.json"

    def listar(self) -> List[Dict[str, Any]]:
        if not self.caminho_indice.exists():
            return []
        return json.loads(self.caminho_indice.read_text(encoding="utf-8"))

    def _salvar(self, perfis: List[Dict[str, Any]]) -> None:
        self.caminho_indice.write_text(
            json.dumps(perfis, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def registrar(
        self,
        nome: str,
        agente_id: str,
        audio: bytes,
        consentimento: str,
        idioma: str = "pt-BR",
    ) -> PerfilVoz:
        if str(consentimento).strip().upper() != CONSENTIMENTO_FRASE:
            raise PermissionError(
                "É necessário confirmar: " + CONSENTIMENTO_FRASE
            )
        if len(audio) < 1000 or len(audio) > 20_000_000:
            raise ValueError("Amostra de voz inválida.")
        try:
            with wave.open(__import__("io").BytesIO(audio), "rb") as wav:
                if wav.getnframes() < 1000:
                    raise ValueError("Amostra muito curta.")
        except Exception as erro:  # noqa: BLE001
            raise ValueError("Amostra WAV inválida.") from erro

        perfil = PerfilVoz(
            id=novo_id("voz_"),
            nome=str(nome or "").strip()[:80],
            agente_id=agente_id,
            idioma=idioma,
            criado_em=agora_iso(),
            arquivo="",
            consentimento=CONSENTIMENTO_FRASE,
        )
        if not perfil.nome:
            raise ValueError("Nome obrigatório.")
        arquivo = self.diretorio / (perfil.id + ".wav")
        arquivo.write_bytes(audio)
        perfil.arquivo = arquivo.name
        perfis = self.listar()
        perfis.append(perfil.para_dict())
        self._salvar(perfis)
        return perfil

    def excluir(self, perfil_id: str) -> bool:
        perfis = self.listar()
        restantes = [p for p in perfis if p["id"] != perfil_id]
        if len(restantes) == len(perfis):
            return False
        for perfil in perfis:
            if perfil["id"] == perfil_id:
                caminho = self.diretorio / perfil["arquivo"]
                caminho.unlink(missing_ok=True)
        self._salvar(restantes)
        return True

    def estado(self) -> Dict[str, Any]:
        perfis = self.listar()
        return {
            "perfis": len(perfis),
            "habilitado": any(p.get("ativo") for p in perfis),
            "motivo": (
                "Aguardando amostra autorizada do titular."
                if not perfis
                else "Amostra registrada; ativação depende de provedor TTS com clonagem."
            ),
        }
