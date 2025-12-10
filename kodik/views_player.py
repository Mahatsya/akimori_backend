import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


def _client_ip_from_request(request) -> str:
    """Получает IP пользователя (учитывает X-Forwarded-For, если есть)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _normalize_and_validate_link(raw_link: str) -> Tuple[str, str]:
    """
    Возвращает (raw_for_hmac, url_for_api).

    raw_for_hmac — исходная строка (сохраняем //, если так пришло) для подписи.
    url_for_api  — тот же URL с явной схемой https:// для апстрима.

    Разрешаем корни и поддомены: *.kodik.cc, *.kodik.biz, *.kodik.info
    """
    link = (raw_link or "").strip()
    if not link:
        raise ValueError("valid 'link' required")

    allowed_roots = ("kodik.cc", "kodik.biz", "kodik.info")

    if link.startswith("//"):
        https_url = "https:" + link
        parsed = urlparse(https_url)
        host = (parsed.hostname or "").lower()
        if not (host in allowed_roots or any(host.endswith(f".{d}") for d in allowed_roots)):
            raise ValueError("unsupported host")
        return link, https_url

    if link.startswith("http://") or link.startswith("https://"):
        parsed = urlparse(link)
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("invalid link")
        if not (host in allowed_roots or any(host.endswith(f".{d}") for d in allowed_roots)):
            raise ValueError("unsupported host")
        return link, link

    raise ValueError("invalid link format")


class KodikVideoLinkView(APIView):
    """
    GET /api/kodik/video-link/?link=...

    Поведение:
      ✅ skip_segments всегда применяется (true)
      ✅ auto_proxy всегда применяется (true)
      ❌ отключить их нельзя

    Формат подписи: "{raw_link}:{ip}:{YYYYMMDDHH}"
    """

    def get(self, request, *args, **kwargs):
        public = getattr(settings, "KODIK_PUBLIC_KEY", None)
        private = getattr(settings, "KODIK_PRIVATE_KEY", None)
        api_url = getattr(settings, "KODIK_VIDEO_LINKS_URL", None)
        if not public or not private or not api_url:
            return Response(
                {"detail": "KODIK keys or api url are not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            raw_link = request.query_params.get("link", "")
            link_for_hmac, link_for_api = _normalize_and_validate_link(raw_link)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        ip = _client_ip_from_request(request)

        hours = max(1, min(10, int(getattr(settings, "KODIK_DEADLINE_HOURS", 6))))
        deadline = (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y%m%d%H")

        # Подпись строго по исходной строке (сохраняем //)
        msg = f"{link_for_hmac}:{ip}:{deadline}".encode("utf-8")
        digest = hmac.new(private.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        # ВСЕГДА добавляем skip_segments и auto_proxy
        params: Dict[str, Any] = {
            "link": link_for_api,
            "p": public,
            "ip": ip,
            "d": deadline,
            "s": digest,
            "skip_segments": "true",
            "auto_proxy": "true",
        }

        try:
            resp = requests.get(api_url, params=params, timeout=20)
            resp.raise_for_status()
            return Response(resp.json())

        except requests.HTTPError as e:
            body = e.response.text if getattr(e, "response", None) else ""
            safe = {k: v for k, v in params.items() if k != "s"}
            return Response(
                {
                    "detail": f"http_error {getattr(e.response, 'status_code', '?')}",
                    "api_url": api_url,
                    "params": safe,
                    "body": body,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except requests.RequestException as e:
            return Response({"detail": f"upstream_request_failed: {e}"}, status=status.HTTP_502_BAD_GATEWAY)
        except ValueError as e:
            return Response({"detail": f"invalid_json_from_upstream: {e}"}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            return Response({"detail": f"unexpected_error: {e}"}, status=status.HTTP_502_BAD_GATEWAY)
