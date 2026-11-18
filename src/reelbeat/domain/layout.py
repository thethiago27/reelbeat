from __future__ import annotations

import re
from dataclasses import dataclass

LAYOUT_TYPES = ("small", "big", "tall", "stack", "split", "grid", "rows", "blank")
LINE_BREAK = " / "

_SPEC = re.compile(
    r"^\s*(?P<type>[a-z]+)"
    r"(?:\s+(?:x(?P<n>\d+)|(?P<cols>\d+)x(?P<rows>\d+)))?"
    r"\s*(?::\s?(?P<text>.*))?$",
    re.S,
)

_DEFAULTS = {"stack": {"n": 4}, "rows": {"n": 4}, "grid": {"cols": 4, "rows": 9}}


@dataclass(frozen=True)
class Layout:
    """Como um texto ocupa a tela.

    Escrito no roteiro numa linha curta, por exemplo::

        small: UMA VIAGEM POR      texto pequeno centralizado
        big: PORTO / SEGURO        título condensado (" / " quebra a linha)
        tall: BAHIA                letras esticadas até preencher a tela
        stack x9: PORTO SEGURO     a mesma linha repetida 9 vezes
        split: PORTO / SEGURO      uma parte em cima, outra embaixo
        grid 4x9: BA               mosaico de 4 colunas por 9 linhas
        rows x5: TRANCOSO          faixas gigantes vazando da tela
        blank                      só a cor de fundo
    """

    type: str
    text: str = ""
    n: int | None = None
    cols: int | None = None
    rows: int | None = None

    def __post_init__(self) -> None:
        if self.type not in LAYOUT_TYPES:
            raise ValueError(f"layout desconhecido: {self.type!r} (use {', '.join(LAYOUT_TYPES)})")
        if self.type != "blank" and not self.text.strip():
            raise ValueError(f"o layout {self.type!r} precisa de texto")
        for key, value in _DEFAULTS.get(self.type, {}).items():
            if getattr(self, key) is None:
                object.__setattr__(self, key, value)

    @classmethod
    def parse(cls, spec: str | Layout) -> Layout:
        if isinstance(spec, Layout):
            return spec
        m = _SPEC.match(str(spec))
        if not m:
            raise ValueError(f"layout inválido: {spec!r}")
        to_int = lambda v: int(v) if v is not None else None  # noqa: E731
        return cls(
            type=m["type"],
            text=(m["text"] or "").strip(),
            n=to_int(m["n"]),
            cols=to_int(m["cols"]),
            rows=to_int(m["rows"]),
        )

    @property
    def lines(self) -> list[str]:
        parts = re.split(r"\s+/\s+|\n", self.text)
        return [p.strip() for p in parts if p.strip()]

    def __str__(self) -> str:
        head = self.type
        if self.type in ("stack", "rows"):
            head += f" x{self.n}"
        elif self.type == "grid":
            head += f" {self.cols}x{self.rows}"
        return head if self.type == "blank" else f"{head}: {self.text}"


def two_lines(name: str, min_split: int = 7) -> str:
    """Quebra um nome em até duas linhas equilibradas, para títulos grandes.

    "PORTO SEGURO" -> "PORTO / SEGURO"; "TRANCOSO" -> "TRAN / COSO"; "BAHIA" -> "BAHIA".
    """
    words = name.split()
    if not words:
        return name
    if len(words) == 1:
        w = words[0]
        if len(w) < min_split:
            return w
        half = len(w) // 2
        return f"{w[:half]}{LINE_BREAK}{w[half:]}"
    best = min(
        range(1, len(words)),
        key=lambda i: max(len(" ".join(words[:i])), len(" ".join(words[i:]))),
    )
    return f"{' '.join(words[:best])}{LINE_BREAK}{' '.join(words[best:])}"
