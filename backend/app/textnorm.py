"""Chave normalizada de texto (locais) e escolha da grafia a mostrar.

Só serve para ler e agrupar: nunca se reescreve um registo já gravado.
"""
import re
import unicodedata
from datetime import date
from typing import Iterable, Optional

_SPACES = re.compile(r"\s+")


def text_key(value: Optional[str]) -> str:
    """Minúsculas, sem acentos, sem espaços nas pontas e com os repetidos reduzidos a um só."""
    decomposed = unicodedata.normalize("NFKD", (value or "").casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _SPACES.sub(" ", plain).strip()


def group_spellings(rows: Iterable[tuple]) -> dict:
    """rows: (grafia, usos, data do gasto mais recente). Devolve chave -> [nome, usos totais, data mais recente].

    O nome é a grafia mais usada do grupo; em empate, a do gasto mais recente.
    """
    spellings: dict = {}  # chave -> {grafia: [usos, data]}
    for name, uses, last in rows:
        key = text_key(name)
        if not key:
            continue
        seen = spellings.setdefault(key, {}).setdefault(name, [0, date.min])
        seen[0] += uses
        seen[1] = max(seen[1], last or date.min)
    groups = {}
    for key, names in spellings.items():
        best = min(names.items(), key=lambda kv: (-kv[1][0], -kv[1][1].toordinal(), kv[0]))[0]
        groups[key] = [best, sum(u for u, _ in names.values()), max(d for _, d in names.values())]
    return groups
