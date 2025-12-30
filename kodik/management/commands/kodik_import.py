# coding: utf-8
from __future__ import annotations

import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import activate, get_language

# django-countries (необязателен, но очень желателен)
try:
    from django_countries import countries
except Exception:
    countries = None

from kodik.models import (
    Translation,
    Country,
    Genre,
    Studio,
    LicenseOwner,
    MDLTag,
    Person,
    Material,
    MaterialExtra,
    MaterialVersion,
    Season,
    Episode,
    Credit,
)

# =======================================================
# Конфиг по умолчанию (можно переопределить в settings.KODIK_IMPORT)
# =======================================================
DEFAULTS = {
    "TOKEN": "ab83c7000f60d4266448b0507f673163",   # ← твой токен
    "BASE_URL": "https://kodikapi.com/list",
    "LIMIT": 100,
    "TYPES": "anime,anime-serial",  # при желании сузить
    "SORT": "updated_at",
    "ORDER": "desc",
    "WITH_MATERIAL_DATA": True,
    "WITH_EPISODES_DATA": True,   # если выключить — можно включить --with-episodes
    "WITH_PAGE_LINKS": False,     # если нет своего сайта, можно вернуть ссылки на их страницы
    # "NOT_BLOCKED_IN": "RU,UA",
    # Можно строкой "714,720" или [714, 720] или None
    "TRANSLATION_ID": [
        610, 2495, 1354, 3861, 1978, 767, 2823, 2674, 3051,
        3206, 2725, 923, 557, 1068, 1291, 609, 1405, 643, 3805
    ],
    "SLEEP_BETWEEN_PAGES": 0.6,
    "HTTP_TIMEOUT": 30,
    "MAX_PAGES": None,
    "PAGE_HARD_TIMEOUT": 120,
    "VERBOSE_BY_DEFAULT": True,
}

CONFIG: Dict[str, Any] = {**DEFAULTS, **getattr(settings, "KODIK_IMPORT", {})}

# =======================================================
# ЛОГГЕР
# =======================================================
class Log:
    def __init__(self, cmd, enabled: bool):
        self.cmd = cmd
        self.enabled = bool(enabled)

    def info(self, msg: str):
        if self.enabled:
            self.cmd.stdout.write(msg)

    def http(self, msg: str):
        if self.enabled:
            self.cmd.stdout.write(self.cmd.style.HTTP_INFO(msg))

    def note(self, msg: str):
        if self.enabled:
            self.cmd.stdout.write(self.cmd.style.NOTICE(msg))

    def ok(self, msg: str):
        if self.enabled:
            self.cmd.stdout.write(self.cmd.style.SUCCESS(msg))

    def warn(self, msg: str):
        if self.enabled:
            self.cmd.stderr.write(self.cmd.style.WARNING(msg))

    def err(self, msg: str):
        self.cmd.stderr.write(self.cmd.style.ERROR(msg))

# =======================================================
# HTTP с ретраями
# =======================================================
_session: Optional[requests.Session] = None


def _sess() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "aki-importer/1.0 (+https://example.dev)",
            "Accept": "application/json",
        })
        retry = Retry(
            total=5,
            connect=5,
            read=5,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=10,
            pool_maxsize=20,
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _session = s
    return _session


def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = _sess().get(url, params=params, timeout=(10, CONFIG["HTTP_TIMEOUT"]))
    r.raise_for_status()
    return r.json()

# =======================================================
# Вспомогательное: нормализация списка ID (для translation_id)
# =======================================================
def _csv_ids(raw) -> Optional[str]:
    """
    Принимает: None | str "714,720" | int | [714, "720", "721,722"] | set/tuple.
    Возвращает: "714,720,721,722" или None.
    """
    if raw in (None, "", []):
        return None

    tokens: List[str] = []
    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            if item is None:
                continue
            tokens += re.split(r"[,\s]+", str(item).strip())
    else:
        tokens = re.split(r"[,\s]+", str(raw).strip())

    ids: List[int] = []
    for t in tokens:
        if not t:
            continue
        try:
            ids.append(int(t))
        except ValueError:
            continue

    seen = set()
    uniq: List[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            uniq.append(i)

    return ",".join(str(i) for i in uniq) if uniq else None

# =======================================================
# Страны и маппинг локализованных названий → ISO-код
# =======================================================
RUS_ALIASES: Dict[str, str] = {
    "великобритания": "GB", "англия": "GB", "соединенное королевство": "GB", "соединённое королевство": "GB",
    "сша": "US", "штаты": "US", "соединенные штаты": "US", "соединённые штаты": "US",
    "южная корея": "KR", "корея южная": "KR",
    "северная корея": "KP", "корея северная": "KP",
    "россия": "RU", "рф": "RU",
    "япония": "JP",
    "китай": "CN", "кнр": "CN",
    "юар": "ZA", "южно-африканская республика": "ZA",
    "оаэ": "AE", "эмираты": "AE",
    "катар": "QA",
    "турция": "TR",
    "канада": "CA",
    "мексика": "MX",
    "испания": "ES",
    "франция": "FR",
    "германия": "DE",
    "италия": "IT",
    "польша": "PL",
    "нидерланды": "NL", "голландия": "NL",
    "венесуэла": "VE",
    "вьетнам": "VN",
    "таиланд": "TH", "тайланд": "TH",
    "тайвань": "TW",
    "гонконг": "HK",
    "сингапур": "SG",
    "швеция": "SE",
    "швейцария": "CH",
    "норвегия": "NO",
    "дания": "DK",
    "финляндия": "FI",
    "австралия": "AU",
    "бразилия": "BR",
    "чили": "CL",
    "аргентина": "AR",
    "индия": "IN",
    "ирландия": "IE",
    "украина": "UA",
    "беларусь": "BY",
    "казахстан": "KZ",
}


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace("ё", "е")


def _country_code_from_ru(name: str) -> Optional[str]:
    if not name:
        return None
    key = _norm(name)

    if key in RUS_ALIASES:
        return RUS_ALIASES[key]

    if countries is None:
        return None

    prev_lang = get_language()
    try:
        activate("ru")
        for code, loc_name in countries:
            if _norm(loc_name) == key:
                return code
        # на случай «Корея, Южная»
        if "," in key:
            a, b = [p.strip() for p in key.split(",", 1)]
            swapped = f"{b} {a}"
            for code, loc_name in countries:
                if _norm(loc_name) == swapped:
                    return code
    finally:
        if prev_lang:
            activate(prev_lang)

    return None


def _ensure_country_by_code(code: str, name_fallback: Optional[str] = None) -> Country:
    code = (code or "").strip().upper()[:2] or "XX"
    obj, created = Country.objects.get_or_create(code=code, defaults={"name": name_fallback or code})
    if created and not obj.name:
        obj.name = name_fallback or code
        obj.save(update_fields=["name"])
    return obj


def _ensure_country_by_name(name: str) -> Country:
    name = (name or "").strip()
    if not name:
        return _ensure_country_by_code("XX", "Unknown")

    existing = Country.objects.filter(name=name).first()
    if existing:
        return existing

    code = _country_code_from_ru(name)
    if code:
        return _ensure_country_by_code(code, name_fallback=name)

    # fall back: синтезируем код
    letters = [c for c in name.upper() if "A" <= c <= "Z"]
    base_code = ("".join(letters) or "XX")[:2]
    code = base_code or "XX"
    i = 2
    while Country.objects.filter(code=code).exists():
        suffix = str(i)
        code = (base_code[0] + suffix)[:2] if len(base_code) >= 1 else ("X" + suffix)[:2]
        i += 1
    return Country.objects.create(code=code, name=name)

# =======================================================
# Парс-хелперы (жанры/люди/теги/студии/владельцы)
# =======================================================
def _ensure_translation(tr: Dict[str, Any]) -> Optional[Translation]:
    if not tr:
        return None
    ext_id = tr.get("id")
    if ext_id is None:
        return None
    title = tr.get("title") or ""
    ttype = tr.get("type") or "voice"
    obj, _ = Translation.objects.get_or_create(ext_id=ext_id, defaults={"title": title, "type": ttype})
    changed = False
    if obj.title != title:
        obj.title = title
        changed = True
    if obj.type != ttype:
        obj.type = ttype
        changed = True
    if changed:
        obj.save()
    return obj


def _ensure_genres(material: Material, data: Dict[str, Any]):
    def add(names: Iterable[str], source: str):
        for n in names or []:
            n = (n or "").strip()
            if n:
                g, _ = Genre.objects.get_or_create(name=n, source=source)
                material.genres.add(g)

    _ensure = data or {}
    add(_ensure.get("genres"), "kp")
    add(_ensure.get("anime_genres"), "shikimori")
    add(_ensure.get("drama_genres"), "mdl")
    add(_ensure.get("all_genres"), "all")


def _ensure_studios(material: Material, names: Iterable[str]):
    for n in names or []:
        n = (n or "").strip()
        if n:
            s, _ = Studio.objects.get_or_create(name=n)
            material.studios.add(s)


def _ensure_license_owners(material: Material, names: Iterable[str]):
    for n in names or []:
        n = (n or "").strip()
        if n:
            s, _ = LicenseOwner.objects.get_or_create(name=n)
            material.license_owners.add(s)


def _ensure_mdl_tags(material: Material, names: Iterable[str]):
    for n in names or []:
        n = (n or "").strip()
        if n:
            t, _ = MDLTag.objects.get_or_create(name=n)
            material.mdl_tags.add(t)


def _ensure_people(material: Material, role: str, names: Iterable[str]):
    for n in names or []:
        n = (n or "").strip()
        if n:
            p, _ = Person.objects.get_or_create(name=n)
            Credit.objects.get_or_create(material=material, person=p, role=role)

# =======================================================
# Утилиты дат
# =======================================================
def _parse_date_safe(value: Optional[str]):
    if not value:
        return None
    try:
        return parse_date(value)
    except Exception:
        return None


def _parse_dt_safe(value: Optional[str]):
    if not value:
        return None
    try:
        return parse_datetime(value)
    except Exception:
        return None

# =======================================================
# Поиск уже сохранённого материала по внешним ID
# =======================================================
def _find_existing_by_external_ids(payload: Dict[str, Any]) -> Optional[Material]:
    ids = {
        "kinopoisk_id": (payload.get("kinopoisk_id") or "").strip(),
        "imdb_id": (payload.get("imdb_id") or "").strip(),
        "mdl_id": (payload.get("mdl_id") or "").strip(),
        "shikimori_id": (payload.get("shikimori_id") or "").strip(),
    }
    worldart_link = (payload.get("worldart_link") or "").strip()

    q = Material.objects.all()
    for field in ("kinopoisk_id", "imdb_id", "mdl_id", "shikimori_id"):
        val = ids.get(field)
        if val:
            obj = q.filter(**{field: val}).first()
            if obj:
                return obj
    if worldart_link:
        obj = q.filter(worldart_link=worldart_link).first()
        if obj:
            return obj
    return None

# =======================================================
# UPSERT: Material (без extra/relations)
# =======================================================
def _upsert_material(item: Dict[str, Any]) -> Tuple[Material, bool]:
    kodik_id = item.get("id")
    title = item.get("title") or ""
    title_orig = item.get("title_orig") or ""
    other_title = item.get("other_title") or ""
    type_ = item.get("type") or ""
    link = item.get("link") or ""

    year = item.get("year")
    quality = item.get("quality") or ""
    camrip = item.get("camrip")
    lgbt = item.get("lgbt")

    kinopoisk_id = (item.get("kinopoisk_id") or "").strip()
    imdb_id = (item.get("imdb_id") or "").strip()
    mdl_id = (item.get("mdl_id") or "").strip()
    worldart_link = (item.get("worldart_link") or "").strip()
    shikimori_id = (item.get("shikimori_id") or "").strip()

    created_at = _parse_dt_safe(item.get("created_at"))
    updated_at = _parse_dt_safe(item.get("updated_at"))

    main_translation = _ensure_translation(item.get("translation"))

    obj = Material.objects.filter(pk=kodik_id).first()
    if not obj:
        obj = _find_existing_by_external_ids(item)

    created = False
    if not obj:
        obj = Material(
            kodik_id=kodik_id,
            type=type_,
            link=link,  # для сериалов — не используется, для фильмов — legacy
            title=title,
            title_orig=title_orig,
            other_title=other_title,
            translation=main_translation,
            year=year or None,
            quality=quality,
            camrip=camrip,
            lgbt=lgbt,
            kinopoisk_id=kinopoisk_id,
            imdb_id=imdb_id,
            mdl_id=mdl_id,
            worldart_link=worldart_link,
            shikimori_id=shikimori_id,
        )
        if created_at:
            obj.created_at = created_at
        if updated_at:
            obj.updated_at = updated_at
        obj.poster_url = ""
        obj.save()
        created = True
    else:
        changed = False
        for field, val in [
            ("type", type_),
            ("link", link),
            ("title", title),
            ("title_orig", title_orig),
            ("other_title", other_title),
            ("translation", main_translation),
            ("year", year or None),
            ("quality", quality),
            ("camrip", camrip),
            ("lgbt", lgbt),
            ("kinopoisk_id", kinopoisk_id),
            ("imdb_id", imdb_id),
            ("mdl_id", mdl_id),
            ("worldart_link", worldart_link),
            ("shikimori_id", shikimori_id),
        ]:
            if getattr(obj, field) != val:
                setattr(obj, field, val)
                changed = True
        if created_at and obj.created_at != created_at:
            obj.created_at = created_at
            changed = True
        if updated_at and obj.updated_at != updated_at:
            obj.updated_at = updated_at
            changed = True
        if changed:
            obj.save()

    # блокировки по странам (коды ISO из API)
    for cc in item.get("blocked_countries") or []:
        obj.blocked_countries.add(_ensure_country_by_code(cc))

    # базовые скриншоты
    scr = item.get("screenshots") or []
    if isinstance(scr, list) and len(scr) > 200:
        scr = scr[:200]
    if scr and obj.screenshots != scr:
        obj.screenshots = scr
        obj.save(update_fields=["screenshots"])

    # агрегаты сериалов
    agg_changed = False
    ls = item.get("last_season")
    le = item.get("last_episode")
    ec = item.get("episodes_count")
    if isinstance(ls, int) and obj.last_season != ls:
        obj.last_season = ls
        agg_changed = True
    if isinstance(le, int) and obj.last_episode != le:
        obj.last_episode = le
        agg_changed = True
    if isinstance(ec, int) and obj.episodes_count != ec:
        obj.episodes_count = ec
        agg_changed = True
    if agg_changed:
        obj.save(update_fields=["last_season", "last_episode", "episodes_count"])

    # блокировки сезонов
    if isinstance(item.get("blocked_seasons"), dict) and item["blocked_seasons"]:
        obj.blocked_seasons = item["blocked_seasons"]
        obj.save(update_fields=["blocked_seasons"])

    return obj, created

# =======================================================
# UPSERT: MaterialExtra + связи (страны, жанры, студии, владельцы, теги, кредиты)
# =======================================================
def _upsert_extra_and_relations(material: Material, material_data: Optional[Dict[str, Any]]):
    if not material_data:
        return

    extra, _ = MaterialExtra.objects.get_or_create(material=material)

    # простые копирования
    for f in (
        "title", "anime_title", "title_en",
        "other_titles", "other_titles_en", "other_titles_jp",
        "anime_license_name", "anime_kind",
        "all_status", "anime_status", "drama_status",
        "tagline", "description", "anime_description",
        "poster_url", "anime_poster_url", "drama_poster_url",
        "rating_mpaa",
    ):
        v = material_data.get(f)
        if v not in (None, "", []):
            setattr(extra, f, v)

    # числа
    for f in (
        "kinopoisk_rating", "kinopoisk_votes",
        "imdb_rating", "imdb_votes",
        "shikimori_rating", "shikimori_votes",
        "mydramalist_rating", "mydramalist_votes",
        "minimal_age", "episodes_total", "episodes_aired",
    ):
        if material_data.get(f) is not None:
            setattr(extra, f, material_data.get(f))

    if material_data.get("duration") is not None:
        extra.duration = material_data.get("duration")

    # даты
    extra.premiere_ru = _parse_date_safe(material_data.get("premiere_ru"))
    extra.premiere_world = _parse_date_safe(material_data.get("premiere_world"))
    extra.aired_at = _parse_date_safe(material_data.get("aired_at"))
    extra.released_at = _parse_date_safe(material_data.get("released_at"))
    extra.next_episode_at = _parse_dt_safe(material_data.get("next_episode_at"))

    extra.save()

    # быстрый постер в Material
    if extra.poster_url and material.poster_url != extra.poster_url:
        material.poster_url = extra.poster_url
        material.save(update_fields=["poster_url"])

    # страны производства
    for name in material_data.get("countries") or []:
        material.production_countries.add(_ensure_country_by_name(name))

    # жанры / студии / владельцы / MDL-теги
    _ensure_genres(material, material_data)
    _ensure_studios(material, material_data.get("anime_studios"))
    _ensure_license_owners(material, material_data.get("anime_licensed_by"))
    _ensure_mdl_tags(material, material_data.get("mydramalist_tags"))

    # кредиты
    _ensure_people(material, "actor", material_data.get("actors"))
    _ensure_people(material, "director", material_data.get("directors"))
    _ensure_people(material, "producer", material_data.get("producers"))
    _ensure_people(material, "writer", material_data.get("writers"))
    _ensure_people(material, "composer", material_data.get("composers"))
    _ensure_people(material, "editor", material_data.get("editors"))
    _ensure_people(material, "designer", material_data.get("designers"))
    _ensure_people(material, "operator", material_data.get("operators"))

# =======================================================
# Нормализация скриншотов эпизодов
# =======================================================
def _norm_shots(val):
    if not val:
        return []
    out: List[str] = []
    try:
        for x in val:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                for k in ("url", "src", "href"):
                    v = x.get(k)
                    if isinstance(v, str):
                        out.append(v)
                        break
    except Exception:
        pass
    return out[:50] if len(out) > 50 else out

# =======================================================
# UPSERT: версии/сезоны/эпизоды
#  — ВАЖНО: если материал — ФИЛЬМ, создаём Season #1 / Episode #1, где Episode.link = фильм
# =======================================================
SERIAL_TYPES = {
    "cartoon-serial", "documentary-serial", "russian-serial",
    "foreign-serial", "anime-serial", "multi-part-film",
}


def _is_serial(item: Dict[str, Any], material: Material) -> bool:
    if material.type in SERIAL_TYPES:
        return True
    # иногда API неявно (есть seasons/episodes или last_season)
    if isinstance(item.get("seasons"), dict) and item["seasons"]:
        return True
    if item.get("last_season") is not None:
        return True
    return False


def _upsert_versions_seasons_episodes(material: Material, item: Dict[str, Any]):
    """
    Для сериалов:
        - создаём MaterialVersion на перевод
        - создаём/обновляем Season и Episode по данным seasons/episodes

    Для фильмов:
        - пишем ссылку в MaterialVersion.movie_link
        - создаём "виртуальный" сезон №1 и эпизод №1,
          где Episode.link = ссылка на фильм
    """
    # перевод текущего «среза» результата
    tr = _ensure_translation(item.get("translation"))
    if not tr:
        return

    version, _ = MaterialVersion.objects.get_or_create(material=material, translation=tr)

    # ----- ФИЛЬМ -----
    if not _is_serial(item, material):
        link = (item.get("link") or "").strip()
        if not link:
            return

        # 1) сохраняем как movie_link (legacy/удобный доступ)
        if version.movie_link != link:
            version.movie_link = link
            version.save(update_fields=["movie_link"])

        # 2) создаём "виртуальный" сезон №1
        season, created_season = Season.objects.get_or_create(
            version=version,
            number=1,
            defaults={"link": link},
        )
        if not created_season and link and season.link != link:
            season.link = link
            season.save(update_fields=["link"])

        # 3) создаём/обновляем эпизод №1
        film_title = material.title or (item.get("title") or "")
        screenshots = _norm_shots(item.get("screenshots"))

        episode, created_episode = Episode.objects.get_or_create(
            season=season,
            number=1,
            defaults={
                "link": link,
                "title": film_title,
                "screenshots": screenshots,
            },
        )

        changed = False
        if link and episode.link != link:
            episode.link = link
            changed = True
        if film_title and episode.title != film_title:
            episode.title = film_title
            changed = True
        if screenshots and episode.screenshots != screenshots:
            episode.screenshots = screenshots
            changed = True
        if changed and not created_episode:
            episode.save(update_fields=["link", "title", "screenshots"])

        # для фильмов на этом всё
        return

    # ----- СЕРИАЛ -----
    seasons_payload = item.get("seasons")
    if not isinstance(seasons_payload, dict):
        return

    # Предзагрузка сезонов и эпизодов
    existing_seasons = {
        s.number: s
        for s in Season.objects.filter(version=version)
    }
    existing_eps_map: Dict[int, Dict[int, Episode]] = {}
    for s in existing_seasons.values():
        eps = Episode.objects.filter(season=s).only(
            "id", "season_id", "number", "link", "title", "screenshots"
        )
        existing_eps_map[s.number] = {e.number: e for e in eps}

    # Сезоны
    to_create_seasons: List[Season] = []
    for season_num_str, season_payload in seasons_payload.items():
        try:
            s_num = int(season_num_str)
        except Exception:
            continue

        s_link = ""
        if isinstance(season_payload, dict):
            s_link = season_payload.get("link") or ""

        season = existing_seasons.get(s_num)
        if not season:
            to_create_seasons.append(Season(version=version, number=s_num, link=s_link))
        else:
            if s_link and season.link != s_link:
                season.link = s_link
                season.save(update_fields=["link"])

    if to_create_seasons:
        Season.objects.bulk_create(to_create_seasons, ignore_conflicts=True)
        fresh = Season.objects.filter(
            version=version,
            number__in=[s.number for s in to_create_seasons],
        )
        for s in fresh:
            existing_seasons[s.number] = s

    # Эпизоды
    for s in existing_seasons.values():
        if s.number not in existing_eps_map:
            eps = Episode.objects.filter(season=s).only(
                "id", "season_id", "number", "link", "title", "screenshots"
            )
            existing_eps_map[s.number] = {e.number: e for e in eps}

    eps_bulk_create: List[Episode] = []
    eps_bulk_update: List[Episode] = []

    for season_num_str, season_payload in seasons_payload.items():
        try:
            s_num = int(season_num_str)
        except Exception:
            continue
        season = existing_seasons.get(s_num)
        if not season:
            continue

        eps_map = existing_eps_map.get(s_num, {})

        episodes = {}
        if isinstance(season_payload, dict):
            episodes = season_payload.get("episodes") or {}

        for ep_num_str, ep_data in episodes.items():
            try:
                e_num = int(ep_num_str)
            except Exception:
                continue

            if isinstance(ep_data, dict):
                link = ep_data.get("link") or ""
                title = ep_data.get("title") or ""
                screenshots = _norm_shots(ep_data.get("screenshots"))
            else:
                link = str(ep_data)
                title = ""
                screenshots = []

            cur = eps_map.get(e_num)
            if not cur:
                eps_bulk_create.append(
                    Episode(
                        season=season,
                        number=e_num,
                        link=link,
                        title=title,
                        screenshots=screenshots,
                    )
                )
                eps_map[e_num] = Episode(season=season, number=e_num)  # плейсхолдер
            else:
                changed = False
                if link and cur.link != link:
                    cur.link = link
                    changed = True
                if title and cur.title != title:
                    cur.title = title
                    changed = True
                if screenshots and cur.screenshots != screenshots:
                    cur.screenshots = screenshots
                    changed = True
                if changed:
                    eps_bulk_update.append(cur)

    if eps_bulk_create:
        Episode.objects.bulk_create(eps_bulk_create, ignore_conflicts=True)
    if eps_bulk_update:
        Episode.objects.bulk_update(eps_bulk_update, ["link", "title", "screenshots"])

# =======================================================
# КОМАНДА
# =======================================================
class Command(BaseCommand):
    help = (
        "Импорт из Kodik /list: материалы, extra, версии переводов, сезоны/серии. "
        "Для фильмов — ссылка в MaterialVersion.movie_link и Episode #1."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--token", type=str, help="API токен Kodik")
        parser.add_argument("--types", type=str, help="Типы материалов (через запятую)")
        parser.add_argument("--limit", type=int, help="Лимит на страницу (1..100)")
        parser.add_argument("--sort", type=str, help="Поле сортировки")
        parser.add_argument("--order", type=str, help="asc|desc")
        parser.add_argument("--pages", type=int, help="Сколько страниц импортировать")
        parser.add_argument("--with-material-data", action="store_true", help="Тянуть material_data")
        parser.add_argument("--with-episodes-data", action="store_true", help="Тянуть episodes_data (объекты серий)")
        parser.add_argument("--with-episodes", action="store_true", help="Тянуть episodes (только ссылки серий)")
        parser.add_argument(
            "--with-page-links",
            action="store_true",
            help="Заменить все ссылки на страницы плееров Kodik (with_page_links=true)",
        )
        parser.add_argument("--not-blocked-in", type=str, help="Страны через запятую (RU,UA)")
        parser.add_argument(
            "--translation-id",
            dest="translation_id",
            action="append",
            help="ID озвучки (можно несколько: --translation-id 714 --translation-id 720 или строкой '714,720')",
        )
        parser.add_argument("--dry-run", action="store_true", help="Не писать в БД")
        parser.add_argument("--sleep", type=float, help="Пауза между страницами (сек)")
        parser.add_argument("--verbose", action="store_true", help="Подробные логи")
        parser.add_argument("--quiet", action="store_true", help="Минимум логов")

    def handle(self, *args, **options):
        # countries — желателен, но можно работать и без него
        if countries is None:
            self.stderr.write(self.style.WARNING(
                "Внимание: пакет django-countries не установлен. "
                "Маппинг стран будет ограничен. Установи:\n"
                "    pip install django-countries\n"
                "и добавь 'django_countries' в INSTALLED_APPS."
            ))

        activate("ru")  # для локализованного маппинга стран

        verbose = CONFIG["VERBOSE_BY_DEFAULT"]
        if options.get("verbose"):
            verbose = True
        if options.get("quiet"):
            verbose = False
        log = Log(self, verbose)

        token = options.get("token") or CONFIG["TOKEN"]
        if not token:
            log.err("Укажи API токен через --token или в settings.KODIK_IMPORT['TOKEN']")
            return

        params: Dict[str, Any] = {
            "token": token,
            "limit": options.get("limit") or CONFIG["LIMIT"],
            "sort": options.get("sort") or CONFIG["SORT"],
            "order": options.get("order") or CONFIG["ORDER"],
            "types": options.get("types") or CONFIG["TYPES"],
        }

        # фильтр по озвучке (translation_id)
        tr_ids_raw = (
            options.get("translation_id")
            or CONFIG.get("TRANSLATION_ID")
            or CONFIG.get("TRANSLATION_IDS")
        )
        tr_ids_csv = _csv_ids(tr_ids_raw)
        if tr_ids_csv:
            params["translation_id"] = tr_ids_csv

        # включаем подробность среза
        if options.get("with_episodes_data") or CONFIG["WITH_EPISODES_DATA"]:
            params["with_episodes_data"] = "true"
        elif options.get("with_episodes"):
            params["with_episodes"] = "true"

        if options.get("with_material_data") or CONFIG["WITH_MATERIAL_DATA"]:
            params["with_material_data"] = "true"

        if options.get("with_page_links") or CONFIG["WITH_PAGE_LINKS"]:
            params["with_page_links"] = "true"

        nbi = options.get("not_blocked_in") or CONFIG.get("NOT_BLOCKED_IN")
        if nbi:
            params["not_blocked_in"] = nbi

        sleep_pause = options.get("sleep")
        if sleep_pause is None:
            sleep_pause = CONFIG["SLEEP_BETWEEN_PAGES"]

        base_url = CONFIG["BASE_URL"]
        dry_run = bool(options.get("dry_run"))
        max_pages = options.get("pages") or CONFIG.get("MAX_PAGES")
        page_hard_timeout = CONFIG.get("PAGE_HARD_TIMEOUT", 120)

        page_count = 0
        total_processed = 0
        total_created = 0
        total_updated = 0

        next_url = base_url
        next_params = dict(params)
        seen_urls = set()

        log.note(
            f"Старт импорта из {base_url} "
            f"types={next_params.get('types')} "
            f"tr_id={next_params.get('translation_id', '—')}"
        )

        while next_url:
            if next_url in seen_urls:
                log.warn(f"Повторяющийся next_url, выходим: {next_url}")
                break
            seen_urls.add(next_url)

            page_count += 1
            if max_pages and page_count > max_pages:
                break

            log.http(f"[{page_count}] GET {next_url} params={next_params or '-'}")
            try:
                data = _get(next_url, next_params)
            except Exception as e:
                log.err(f"[{page_count}] Ошибка запроса: {e}. Повтор через 2с...")
                time.sleep(2.0)
                data = _get(next_url, next_params)

            results: List[Dict[str, Any]] = data.get("results") or []
            log.info(f"Получено {len(results)} материалов.")

            if dry_run:
                total_processed += len(results)
            else:
                page_started_at = time.perf_counter()
                for i, item in enumerate(results, 1):
                    if time.perf_counter() - page_started_at > page_hard_timeout:
                        log.warn(
                            f"[{page_count}] Превышен таймаут {page_hard_timeout}s "
                            f"на странице — остаток пропущен."
                        )
                        break

                    if i <= 20 and log.enabled:
                        ident = item.get("id") or item.get("slug") or item.get("title") or "<?>"
                        log.info(f"[{page_count}:{i}] start id={ident}")

                    t0 = time.perf_counter()
                    try:
                        material, created = _upsert_material(item)
                        if created:
                            total_created += 1
                        else:
                            total_updated += 1

                        _upsert_extra_and_relations(material, item.get("material_data"))
                        _upsert_versions_seasons_episodes(material, item)

                        if item.get("updated_at"):
                            dt = parse_datetime(item["updated_at"])
                            if dt and material.updated_at != dt:
                                material.updated_at = dt
                                material.save(update_fields=["updated_at"])
                    except Exception as e:
                        ident = item.get("id") or item.get("slug") or item.get("title") or "<?>"
                        log.err(f"[{page_count}:{i}] Ошибка на материале {ident}: {e}")
                        continue

                    dt = time.perf_counter() - t0
                    if i <= 20 and log.enabled:
                        log.info(f"[{page_count}:{i}] ok in {dt:.2f}s")
                    if log.enabled and i % 10 == 0:
                        log.info(
                            f"[{page_count}] обработано {i}/{len(results)} "
                            f"(последний {dt:.2f}s)"
                        )
                    if log.enabled and dt > 2.5:
                        ident = item.get("id") or item.get("slug") or item.get("title") or "<?>"
                        log.warn(f"[{page_count}:{i}] Долго ({dt:.2f}s) на {ident}")

                total_processed += len(results)

            next_page = data.get("next_page")
            log.note(f"next_page: {next_page or '—'}")

            if next_page:
                next_url = next_page
                next_params = {}
            else:
                next_url = None

            if sleep_pause:
                time.sleep(max(0.5, float(sleep_pause)))

        log.ok(
            f"Готово. Страниц: {page_count}, обработано: {total_processed}, "
            f"создано: {total_created}, обновлено: {total_updated}"
        )
