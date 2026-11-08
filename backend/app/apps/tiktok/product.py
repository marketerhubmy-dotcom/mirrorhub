"""
TikTok Shop Product Manager.

Responsibilities:
- Store product mapping (id → name, search_term, sku)
- Resolve product IDs from a job dict
- Validate a product exists before execution
- Persist to a JSON file next to the module so products survive restarts
- Support multiple products; never hardcode product data

Usage:
    from app.apps.tiktok.product import product_manager

    product_manager.add("P001", name="Sabun Wajah X", search_term="Sabun Wajah X")
    p = product_manager.get("P001")
    product_manager.remove("P001")
"""
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from app.core import runtime_paths

_STORE_FILE = runtime_paths.data_dir() / "products.json"


@dataclass
class TikTokProduct:
    id: str
    name: str
    search_term: str    # text to type into TikTok Shop search
    sku: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ProductManager:
    """In-memory product registry backed by a JSON file."""

    def __init__(self, store_file: Path = _STORE_FILE) -> None:
        self._file = store_file
        self._products: dict[str, TikTokProduct] = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                for item in data:
                    p = TikTokProduct(**item)
                    self._products[p.id] = p
            except Exception:
                pass

    def _save(self) -> None:
        try:
            self._file.write_text(
                json.dumps([p.to_dict() for p in self._products.values()], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(
        self,
        product_id: str,
        *,
        name: str,
        search_term: str,
        sku: str = "",
        notes: str = "",
    ) -> TikTokProduct:
        p = TikTokProduct(id=product_id, name=name, search_term=search_term, sku=sku, notes=notes)
        self._products[product_id] = p
        self._save()
        return p

    def update(self, product_id: str, **fields) -> TikTokProduct | None:
        p = self._products.get(product_id)
        if not p:
            return None
        for k, v in fields.items():
            if hasattr(p, k):
                setattr(p, k, v)
        self._save()
        return p

    def get(self, product_id: str) -> TikTokProduct | None:
        return self._products.get(product_id)

    def list_all(self) -> list[TikTokProduct]:
        return list(self._products.values())

    def remove(self, product_id: str) -> bool:
        if product_id in self._products:
            del self._products[product_id]
            self._save()
            return True
        return False

    # ── Resolution ────────────────────────────────────────────────────────────

    def resolve(self, job: dict) -> TikTokProduct | None:
        """
        Extract a TikTokProduct from a job dict.

        Tries in order:
          1. job["product_id"] — look up by registered ID
          2. job["product"] — inline dict with at least {id, name, search_term}
        """
        pid = job.get("product_id", "").strip()
        if pid:
            return self.get(pid)

        inline = job.get("product")
        if isinstance(inline, dict) and inline.get("id"):
            return TikTokProduct(
                id=inline["id"],
                name=inline.get("name", ""),
                search_term=inline.get("search_term", inline.get("name", "")),
                sku=inline.get("sku", ""),
            )

        return None

    def validate_exists(self, product_id: str) -> bool:
        return product_id in self._products


# Singleton used throughout the plugin
product_manager = ProductManager()
