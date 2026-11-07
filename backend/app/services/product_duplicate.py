"""
Centralized product duplicate detection — MVP 0.5.2

Priority order:
  1. Normalized URL
  2. Platform product_id
  3. Normalized name + shop  (when both sides have a non-empty shop)
  4. Name-only legacy        (when either side has no shop)

Pass exclude_id to skip the current row during edit-conflict checks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import SavedProduct
from app.services.product_scraper import normalize_url

MatchedBy = Literal["url", "product_id", "name_shop", "name_only_legacy", "none"]


@dataclass
class DuplicateResult:
    existing: SavedProduct | None
    matched_by: MatchedBy


def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[,;.!?]+$", "", s)
    return s


async def find_duplicate(
    db: AsyncSession,
    *,
    url: str = "",
    product_id: str | None = None,
    name: str = "",
    shop_name: str = "",
    exclude_id: int | None = None,
) -> DuplicateResult:
    """Find a duplicate SavedProduct. Returns (existing, matched_by) or (None, 'none')."""

    def _excl(p: SavedProduct) -> bool:
        return exclude_id is not None and p.id == exclude_id

    # 1. URL match
    if url.startswith("http"):
        canonical = normalize_url(url)
        res = await db.execute(
            select(SavedProduct).where(SavedProduct.url == canonical)
        )
        p = res.scalar_one_or_none()
        if p and not _excl(p):
            return DuplicateResult(existing=p, matched_by="url")

    # 2. product_id match
    pid = (product_id or "").strip()
    if pid:
        res = await db.execute(
            select(SavedProduct).where(SavedProduct.product_id == pid)
        )
        p = res.scalar_one_or_none()
        if p and not _excl(p):
            return DuplicateResult(existing=p, matched_by="product_id")

    # 3 & 4: name-based matching
    norm_name = normalize_name(name)
    norm_shop = normalize_name(shop_name)

    if norm_name:
        res = await db.execute(select(SavedProduct))
        all_products = [p for p in res.scalars().all() if not _excl(p)]

        # Priority 3: name+shop (both sides must have a non-empty shop)
        if norm_shop:
            match = next(
                (
                    p for p in all_products
                    if normalize_name(p.name) == norm_name
                    and normalize_name(p.shop_name) == norm_shop
                ),
                None,
            )
            if match:
                return DuplicateResult(existing=match, matched_by="name_shop")

        # Priority 4: name-only legacy (one or both sides have no shop)
        for p in all_products:
            if normalize_name(p.name) != norm_name:
                continue
            if not norm_shop or not normalize_name(p.shop_name):
                return DuplicateResult(existing=p, matched_by="name_only_legacy")

    return DuplicateResult(existing=None, matched_by="none")


def conflict_message(matched_by: MatchedBy, existing_name: str) -> str:
    if matched_by == "url":
        return f"Produk '{existing_name}' dengan URL yang sama sudah ada dalam library."
    if matched_by == "product_id":
        return f"Produk '{existing_name}' dengan ID produk yang sama sudah ada dalam library."
    if matched_by == "name_shop":
        return f"Produk '{existing_name}' dari kedai yang sama sudah ada dalam library."
    return f"Produk '{existing_name}' sudah ada dalam library (nama serupa)."
