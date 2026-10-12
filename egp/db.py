"""Minimal Supabase (PostgREST) client for the collector. Uses the service role key, which bypasses RLS,
so it must only run in GitHub Actions with the key from repository secrets."""
import os
import time

import requests


class DB:
    def __init__(self, url: str | None = None, key: str | None = None):
        url = url or os.environ["SUPABASE_URL"]
        key = key or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self.base = url.rstrip("/") + "/rest/v1"
        self.s = requests.Session()
        self.s.headers.update({"apikey": key, "Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"})

    def _check(self, r: requests.Response):
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {r.request.method} {r.url} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.text else None

    def select(self, table: str, **params) -> list:
        return self._check(self.s.get(f"{self.base}/{table}", params=params, timeout=60))

    def insert(self, table: str, rows, returning: bool = True):
        prefer = "return=representation" if returning else "return=minimal"
        return self._check(self.s.post(f"{self.base}/{table}", json=rows, headers={"Prefer": prefer}, timeout=60))

    def upsert(self, table: str, rows: list, on_conflict: str):
        return self._check(self.s.post(
            f"{self.base}/{table}", params={"on_conflict": on_conflict}, json=rows,
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"}, timeout=120))

    def update(self, table: str, values: dict, **filters):
        return self._check(self.s.patch(f"{self.base}/{table}", params=filters, json=values,
                                        headers={"Prefer": "return=minimal"}, timeout=60))

    def rpc(self, fn: str, args: dict, retries: int = 3):
        """Our RPCs are idempotent (upserts / reads), so a timed-out call is safe to repeat."""
        for attempt in range(retries + 1):
            try:
                return self._check(self.s.post(f"{self.base}/rpc/{fn}", json=args, timeout=90))
            except (requests.ConnectionError, requests.Timeout):
                if attempt == retries:
                    raise
                time.sleep(10 * (attempt + 1))
