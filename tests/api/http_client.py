from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class HttpClient:
    timeout: float = 35.0
    retries: int = 2
    backoff: float = 0.6
    status_forcelist: Iterable[int] = (429, 500, 502, 503, 504)

    def _session(self) -> requests.Session:
        retry = Retry(
            total=self.retries,
            connect=self.retries,
            read=self.retries,
            status=self.retries,
            backoff_factor=self.backoff,
            status_forcelist=self.status_forcelist,
            allowed_methods=("GET", "HEAD"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def get(self, url: str) -> requests.Response:
        session = self._session()
        try:
            return session.get(url, timeout=self.timeout)
        finally:
            session.close()
