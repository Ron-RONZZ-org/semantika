"""FTS5 search configuration.

Vendored from A-core's ``A.data.search.FTSConfig``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class FTSConfig:
    """Configuration for an FTS5 virtual table.

    Attributes:
        table: Content table name.
        fts_columns: Column names in the FTS index.
        fts_table: FTS virtual table name (default: ``{table}_fts``).
        tokenize: Tokenizer for FTS5 (default: ``unicode61``).
        normalize: Optional per-column normalizer callables.
    """

    table: str
    fts_columns: list[str]
    fts_table: str = ""
    tokenize: str = "unicode61"
    normalize: dict[str, Callable[[str], str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fts_table:
            self.fts_table = f"{self.table}_fts"
