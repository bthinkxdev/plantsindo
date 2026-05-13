from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from django.db.models import QuerySet

from ..models import Category


@dataclass(frozen=True)
class CategoryTree:
    by_id: Dict[int, Category]
    children_ids: Dict[Optional[int], List[int]]

    def descendants_of(self, category_id: int, max_depth: int = 10) -> List[int]:
        """
        Returns a stable BFS list of descendants (excluding the root).
        Designed to be cycle-safe even if bad data exists.
        """
        out: List[int] = []
        seen: Set[int] = {category_id}
        q: deque[Tuple[int, int]] = deque()
        for cid in self.children_ids.get(category_id, []):
            q.append((cid, 1))
        while q:
            cid, depth = q.popleft()
            if cid in seen:
                continue
            seen.add(cid)
            out.append(cid)
            if depth >= max_depth:
                continue
            for nxt in self.children_ids.get(cid, []):
                q.append((nxt, depth + 1))
        return out

    def path_for(self, category_id: int, separator: str = " > ", max_depth: int = 10) -> str:
        cat = self.by_id.get(category_id)
        if not cat:
            return ""
        parts = [cat.name]
        seen: Set[int] = {category_id}
        cur = self.by_id.get(getattr(cat, "parent_id", None))
        depth = 0
        while cur is not None and depth < max_depth:
            if cur.pk in seen:
                break
            seen.add(cur.pk)
            parts.append(cur.name)
            cur = self.by_id.get(getattr(cur, "parent_id", None))
            depth += 1
        return separator.join(reversed(parts))


def build_active_category_tree(qs: Optional[QuerySet] = None) -> CategoryTree:
    if qs is None:
        qs = Category.objects.filter(is_active=True)
    cats = list(qs.only("id", "name", "slug", "parent_id", "is_active").order_by("name", "id"))
    by_id: Dict[int, Category] = {c.pk: c for c in cats if c.pk}
    children_ids: Dict[Optional[int], List[int]] = defaultdict(list)
    for c in cats:
        children_ids[getattr(c, "parent_id", None)].append(c.pk)
    return CategoryTree(by_id=by_id, children_ids=dict(children_ids))


def category_filter_ids_for_slug(category_slug: str, *, include_children: bool = True, max_depth: int = 10) -> Tuple[Optional[Category], List[int]]:
    """
    Returns (category, ids_to_filter_by).

    - If slug is invalid: (None, []).
    - If include_children=True: ids include the selected category and its descendants.
    """
    if not category_slug:
        return (None, [])
    category = Category.objects.filter(slug=category_slug).only("id", "name", "slug", "parent_id", "is_active").first()
    if not category:
        return (None, [])
    if not include_children:
        return (category, [category.pk])
    tree = build_active_category_tree()
    ids = [category.pk] + tree.descendants_of(category.pk, max_depth=max_depth)
    return (category, ids)

