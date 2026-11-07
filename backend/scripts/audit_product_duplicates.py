"""
Audit saved_products for potential duplicate entries.

Usage:
    python scripts/audit_product_duplicates.py

Output only — no records are modified or deleted.
"""
import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiosqlite

DB_PATH = Path(__file__).parent.parent / "mirrorhub.db"


def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[,;.!?]+$", "", s)
    return s


async def main() -> None:
    if not DB_PATH.exists():
        print("mirrorhub.db not found — nothing to audit.")
        return

    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT id, name, url, product_id, shop_name FROM saved_products ORDER BY id"
        )
        rows = [dict(r) for r in await cur.fetchall()]

    issues: list[str] = []

    # Same normalized URL
    by_url: dict[str, list[dict]] = defaultdict(list)
    for p in rows:
        url = (p["url"] or "").strip()
        if url.startswith("http"):
            by_url[url].append(p)
    for url, group in by_url.items():
        if len(group) > 1:
            ids = [g["id"] for g in group]
            issues.append(f"SAME URL       ids={ids}  url={url}")

    # Same product_id
    by_pid: dict[str, list[dict]] = defaultdict(list)
    for p in rows:
        pid = (p["product_id"] or "").strip()
        if pid:
            by_pid[pid].append(p)
    for pid, group in by_pid.items():
        if len(group) > 1:
            ids = [g["id"] for g in group]
            issues.append(f"SAME PRODUCT_ID ids={ids}  product_id={pid}")

    # Same normalized name + shop
    by_name_shop: dict[tuple, list[dict]] = defaultdict(list)
    for p in rows:
        nn = normalize_name(p["name"])
        ns = normalize_name(p["shop_name"])
        if nn and ns:
            by_name_shop[(nn, ns)].append(p)
    for (nn, ns), group in by_name_shop.items():
        if len(group) > 1:
            ids = [g["id"] for g in group]
            issues.append(f"SAME NAME+SHOP ids={ids}  name={nn!r}  shop={ns!r}")

    # Same normalized name with no shop (legacy)
    by_name_noshop: dict[str, list[dict]] = defaultdict(list)
    for p in rows:
        nn = normalize_name(p["name"])
        ns = normalize_name(p["shop_name"])
        if nn and not ns:
            by_name_noshop[nn].append(p)
    for nn, group in by_name_noshop.items():
        if len(group) > 1:
            ids = [g["id"] for g in group]
            issues.append(f"SAME NAME(noshop) ids={ids}  name={nn!r}")

    print(f"=== Product Duplicate Audit ===")
    print(f"Total products: {len(rows)}")
    print(f"Issues found:   {len(issues)}")
    if not issues:
        print("No duplicates detected.")
    else:
        for issue in issues:
            print(f"  ⚠  {issue}")
    print("=== No records were modified. ===")


asyncio.run(main())
