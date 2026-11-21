"""Pure lexical evidence extractors for manuals and curated KB chunks (spec §4)."""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.consultant.knowledge_facts import KbFact
from app.guardrails.output import pt_br_number
from app.models.schemas import CatalogProduct, RetrievedChunk
from app.recommendation.intent import folded

logger = logging.getLogger(__name__)

_GAME_ROW_RE = re.compile(
    r"^\|\s*(?P<game>[^|]+?)\s*\|\s*(?P<res>\d{3,4}p)\s*\|\s*(?P<preset>[^|]+?)\s*\|\s*(?P<fps>\d+)\s*fps\s*\|$",
    re.MULTILINE | re.IGNORECASE,
)
_KB_MEASURE_ROW_RE = re.compile(
    r"^\s*\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<value>\d+(?:[.,]\d+)?)\s+(?P<unit>[^|\s]+)\s*\|\s*$",
    re.MULTILINE,
)
_RESOLUTION_RE = re.compile(r"^\s*(\d+)\s*[x×]\s*(\d+)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class GameRow:
    game: str
    resolution: str
    preset: str
    fps: int
    chunk: RetrievedChunk


@dataclass(frozen=True)
class KbMeasure:
    value: Decimal
    unit: str
    chunk: RetrievedChunk


@dataclass(frozen=True)
class KbFactHit:
    sentence: str
    chunk: RetrievedChunk

    @property
    def text(self) -> str:
        return self.sentence


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def parse_game_rows(chunk: RetrievedChunk) -> list[GameRow]:
    rows: list[GameRow] = []
    for match in _GAME_ROW_RE.finditer(chunk.content):
        game_name = match.group("game").strip()
        if game_name.casefold() == "jogo":
            continue
        rows.append(
            GameRow(
                game=game_name,
                resolution=match.group("res").strip(),
                preset=match.group("preset").strip(),
                fps=int(match.group("fps")),
                chunk=chunk,
            )
        )
    return rows


def kb_measure(
    chunks: Sequence[RetrievedChunk], label: str | KbFact | tuple[str, str]
) -> KbMeasure | None:
    target_label = label[1] if isinstance(label, tuple) else label
    folded_target = folded(_normalize_whitespace(target_label))
    if not folded_target:
        return None
    for chunk in chunks:
        for match in _KB_MEASURE_ROW_RE.finditer(chunk.content):
            row_label = folded(_normalize_whitespace(match.group("label")))
            if row_label != folded_target:
                continue
            try:
                parsed = Decimal(pt_br_number(match.group("value").strip()))
            except InvalidOperation:
                continue
            return KbMeasure(
                value=parsed,
                unit=match.group("unit").strip(),
                chunk=chunk,
            )
    return None


def kb_sentence(
    chunks: Sequence[RetrievedChunk], sentence: str | KbFact | tuple[str, str]
) -> RetrievedChunk | None:
    target_sentence = sentence[1] if isinstance(sentence, tuple) else sentence
    wanted = _normalize_whitespace(target_sentence)
    if not wanted:
        return None
    for chunk in chunks:
        if wanted in _normalize_whitespace(chunk.content):
            return chunk
    logger.warning(
        "kb_sentence_missing sentence=%r",
        target_sentence,
        extra={"sentence": target_sentence},
    )
    return None


def webcam_capability(
    product_or_resolution: CatalogProduct | object,
    fps: object = None,
) -> tuple[int, int] | None:
    if isinstance(product_or_resolution, CatalogProduct):
        specs = product_or_resolution.specs_json
        raw_res = specs.get("resolucao")
        raw_fps = specs.get("fps")
    else:
        raw_res = product_or_resolution
        raw_fps = fps
    if not isinstance(raw_res, str) or type(raw_fps) is not int or raw_fps <= 0:
        return None
    match = _RESOLUTION_RE.fullmatch(raw_res)
    if match is None:
        return None
    height = int(match.group(2))
    return (height, raw_fps) if height > 0 else None
