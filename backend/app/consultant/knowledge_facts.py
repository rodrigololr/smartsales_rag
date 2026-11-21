"""Frozen curated knowledge base constants (spec §8 and §11 A2/A3)."""

from typing import NamedTuple


class KbFact(NamedTuple):
    doc_id: str
    text: str


DOC_GTA6_PLATFORMS = "KB-GTA6-PLATAFORMAS"
DOC_GTA_RP = "KB-GTA-RP"
DOC_GTAV_REQUIREMENTS = "KB-GTAV-REQUISITOS"
DOC_ROBLOX_REQUIREMENTS = "KB-ROBLOX-REQUISITOS"
DOC_TWITCH_STREAMING = "KB-TWITCH-TRANSMISSAO"
DOC_SOFA_SPACE = "KB-SOFA-ESPACO"

KB_GTA6_PLATFORMS = KbFact(
    DOC_GTA6_PLATFORMS,
    "GTA 6 foi lançado em 19/11/2026 para PlayStation 5 e Xbox Series X|S.",
)
KB_GTA6_NO_PC = KbFact(
    DOC_GTA6_PLATFORMS,
    "Não há versão de GTA 6 para PC anunciada até a data de atualização desta base.",
)
KB_GTA_RP = KbFact(
    DOC_GTA_RP,
    "GTA RP é jogado no GTA V para PC por meio de servidores de roleplay.",
)
KB_TWITCH_HEIGHT = KbFact(
    DOC_TWITCH_STREAMING,
    "Altura máxima de vídeo recomendada",
)
KB_TWITCH_FPS = KbFact(
    DOC_TWITCH_STREAMING,
    "Taxa de quadros máxima recomendada",
)
KB_SOFA_CLEARANCE = KbFact(
    DOC_SOFA_SPACE,
    "Folga lateral mínima por lado",
)
KB_SOFA_FRONT = KbFact(
    DOC_SOFA_SPACE,
    "Passagem livre mínima à frente",
)
