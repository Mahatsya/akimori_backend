# api/filters_any.py
from __future__ import annotations
from typing import Iterable, Tuple, Dict, Any
from django.db.models import Q, QuerySet
from django_filters import FilterSet
from django.core.exceptions import FieldError
from django.utils.datastructures import MultiValueDictKeyError
from django.http import QueryDict

# Разрешённые lookups (можно расширить по надобности)
ALLOWED_LOOKUPS = {
    "exact", "iexact",
    "contains", "icontains",
    "startswith", "istartswith",
    "endswith", "iendswith",
    "lt", "lte", "gt", "gte",
    "in", "range",
    "isnull",
    "year", "month", "day",  # для дат
    "regex", "iregex",
}

def _coerce_value(raw: str):
    """Приведение строк к bool/int/float/None, остальное вернуть как есть."""
    s = raw.strip()
    if s.lower() in {"null", "none"}:
        return None
    if s.lower() in {"true", "false"}:
        return s.lower() == "true"
    # int
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        try:
            return int(s)
        except Exception:
            pass
    # float
    try:
        if "." in s or "e" in s.lower():
            return float(s)
    except Exception:
        pass
    return raw

def _split_csv(value: str) -> list:
    return [p.strip() for p in (value or "").split(",") if p.strip()]

def _range_tuple(value: str) -> Tuple[Any, Any] | None:
    # "2015..2020" -> ("2015", "2020")
    if ".." in value:
        a, b = value.split("..", 1)
        return (_coerce_value(a), _coerce_value(b))
    return None

class DynamicQueryBuilder:
    """
    Парсит QueryDict в Q-объекты (AND/OR/EXCLUDE) с валидацией.
    """
    def __init__(
        self,
        model,
        allowed_fields: Iterable[str] | str = "__all__",
        allowed_lookups: Iterable[str] = ALLOWED_LOOKUPS,
        reserved_keys: Iterable[str] = (),
        known_filter_keys: Iterable[str] = (),
    ):
        self.model = model
        self.allowed_fields = allowed_fields
        self.allowed_lookups = set(allowed_lookups)
        self.reserved = set(reserved_keys) | set(known_filter_keys)

    def _is_field_allowed(self, path: str) -> bool:
        if self.allowed_fields == "__all__":
            return True
        # поддерживаем маски наподобие "extra__*" или точные имена
        for f in self.allowed_fields:
            if f.endswith("__*"):
                if path.startswith(f[:-3] + "__") or path == f[:-3]:
                    return True
            if path == f:
                return True
        return False

    def _make_q(self, key: str, values: list[str]) -> Tuple[Q | None, Q | None]:
        """
        Вернёт (filter_q, exclude_q) для переданного ключа.
        Примеры ключей:
          - "title" => exact
          - "title__icontains"
          - "year__gte"
          - "not__production_countries__code__in"
          - "or1__title__icontains"
          - "aired_at_from" / "aired_at_to" => gte/lte
        """
        negate = False
        or_group = None
        path = key

        # OR-группа: or1__field__lookup
        if path.startswith("or") and "__" in path:
            # or\d+__
            prefix, rest = path.split("__", 1)
            if prefix[2:].isdigit():
                or_group = prefix
                path = rest  # оставляем field__lookup

        # NOT: not__field__lookup
        if path.startswith("not__"):
            negate = True
            path = path[5:]

        lookup = "exact"
        field_path = path

        # Синонимы *_from/_to
        if path.endswith("_from"):
            field_path = path[:-5]
            lookup = "gte"
        elif path.endswith("_to"):
            field_path = path[:-3]
            lookup = "lte"
        else:
            # Явный __lookup
            if "__" in path:
                parts = path.split("__")
                # последний токен — кандидат на lookup
                cand = parts[-1]
                if cand in self.allowed_lookups:
                    lookup = cand
                    field_path = "__".join(parts[:-1])
                else:
                    field_path = path  # трактуем как exact по полю с __ в имени (вложенности)

        if not self._is_field_allowed(field_path):
            return None, None

        # Значения: учитываем повторяющиеся ключи ?a=1&a=2 и CSV
        flat_vals: list[str] = []
        for v in values:
            if lookup in {"in", "range"}:
                # для in/range CSV ожидаем единичное значение
                flat_vals.append(v)
            else:
                # допускаем CSV как несколько значений exact → превращаем в IN
                if "," in v and lookup == "exact":
                    lookup = "in"
                    flat_vals.append(v)
                else:
                    flat_vals.append(v)

        # Преобразование значений под lookup
        if lookup == "in":
            py_val = _split_csv(flat_vals[-1]) if flat_vals else []
            py_val = [_coerce_value(x) for x in py_val]
        elif lookup == "range":
            r = _range_tuple(flat_vals[-1]) if flat_vals else None
            if not r:
                return None, None
            py_val = r
        else:
            py_val = _coerce_value(flat_vals[-1]) if flat_vals else None

        # Проверка корректности пути/lookup через пробное составление kwargs
        kw = {f"{field_path}__{lookup}" if lookup != "exact" else field_path: py_val}

        try:
            q = Q(**kw)
        except FieldError:
            return None, None

        if negate:
            return None, q
        # Сохраняем OR-группу внутри объекта Q через атрибут (потом соберём)
        if or_group:
            q._or_group = or_group  # type: ignore[attr-defined]
        return q, None

    def build(self, params: QueryDict) -> Tuple[Q, list[Q]]:
        and_q = Q()
        excludes: list[Q] = []
        or_groups: Dict[str, Q] = {}

        for key in params.keys():
            if key in self.reserved:
                continue
            try:
                values = params.getlist(key)
            except MultiValueDictKeyError:
                continue

            q, q_ex = self._make_q(key, values)
            if q_ex is not None:
                excludes.append(q_ex)
            if q is None:
                continue
            group = getattr(q, "_or_group", None)
            if group:
                or_groups[group] = or_groups.get(group, Q()) | q
            else:
                and_q &= q

        # Пришиваем все OR-группы (каждая группа — скобки в AND)
        for qg in or_groups.values():
            and_q &= qg

        return and_q, excludes


class AnyFieldFilterSet(FilterSet):
    """
    Микс-ин для django-filters: сначала применяем обычные фильтры FilterSet,
    затем — динамические по схеме field[/__lookup]=...
    """
    # Переопределяйте в наследниках:
    DYN_ALLOWED_FIELDS: Iterable[str] | str = "__all__"
    DYN_ALLOWED_LOOKUPS: Iterable[str] = ALLOWED_LOOKUPS
    DYN_RESERVED_KEYS: Iterable[str] = ("page", "per_page", "ordering", "sort")

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        qs = super().filter_queryset(queryset)

        builder = DynamicQueryBuilder(
            model=self._meta.model,
            allowed_fields=self.DYN_ALLOWED_FIELDS,
            allowed_lookups=self.DYN_ALLOWED_LOOKUPS,
            reserved_keys=self.DYN_RESERVED_KEYS,
            known_filter_keys=self.filters.keys(),  # не дублируем уже объявленные
        )
        and_q, excludes = builder.build(self.data)

        if and_q.children:
            qs = qs.filter(and_q)
        for ex in excludes:
            qs = qs.exclude(ex)

        return qs.distinct()
