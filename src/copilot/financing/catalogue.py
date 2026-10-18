"""Financing product catalogue: loaded from data/catalogue/products.json and validated.

The catalogue is our own, illustrative and modelled on Singapore SME financing (fictional
lenders). Each product is validated against schemas.FinancingProduct; a bad entry is recorded
with its reason and left out, never silently dropped. load_catalogue(path) is the only entry
point, so a different source (e.g. a lender API) can replace it later.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from copilot.schemas import CopilotModel, FinancingProduct, RejectedRow

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "catalogue" / "products.json"


class Catalogue(CopilotModel):
    disclaimer: str
    products: list[FinancingProduct]
    rejected: list[RejectedRow] = []

    def get(self, product_id: str) -> FinancingProduct | None:
        return next((p for p in self.products if p.id == product_id), None)


def parse_catalogue(raw: dict, file: str = "products.json") -> Catalogue:
    products: list[FinancingProduct] = []
    rejected: list[RejectedRow] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw.get("products", []), start=1):
        try:
            product = FinancingProduct.model_validate(entry)
        except ValidationError as exc:
            reason = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            rejected.append(
                RejectedRow(file=file, line=index, reason=reason, raw={"id": str(entry.get("id"))})
            )
            continue
        if product.id in seen:
            rejected.append(
                RejectedRow(file=file, line=index, reason="duplicate id", raw={"id": product.id})
            )
            continue
        seen.add(product.id)
        products.append(product)
    return Catalogue(disclaimer=raw.get("disclaimer", ""), products=products, rejected=rejected)


@lru_cache(maxsize=4)
def load_catalogue(path: Path = DEFAULT_PATH) -> Catalogue:
    return parse_catalogue(json.loads(path.read_text(encoding="utf-8")), path.name)
