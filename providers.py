"""External source contract and normalized Instagram adapter; no database access."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Observation:
    platform: str
    media_id: str
    published_at: str
    title: str
    metrics: dict
    observed_at: str | None
    cached: bool
    raw: dict


@dataclass(frozen=True)
class Fetch:
    source: str
    fetched_at: str
    observations: list[Observation]
    raw: str


class AnalyticsProvider(Protocol):
    def fetch(self) -> Fetch:
        """Return all available publications/observations and actual fetch provenance."""
        ...


class InstagramProvider:
    """Accept the documented normalized connector envelope, without guessing API aliases."""

    def __init__(self, response, raw=None):
        self.response = response
        self.raw = raw if raw is not None else json.dumps(response)

    @classmethod
    def from_file(cls, path):
        raw = Path(path).read_text(encoding='utf-8-sig')
        return cls(json.loads(raw), raw)

    def fetch(self):
        response = self.response
        if not isinstance(response, dict) or not isinstance(response.get('reels'), list):
            raise ValueError('Provider response requires a reels array')
        observations = []
        for reel in response['reels']:
            if not isinstance(reel, dict):
                raise ValueError('Reel must be an object')
            if reel.get('media_product_type') != 'REELS':
                continue
            if not isinstance(reel.get('metrics', {}), dict):
                raise ValueError('metrics must be an object')
            cached = reel.get('cached', False)
            if not isinstance(cached, bool):
                raise ValueError('cached must be boolean')
            observations.append(Observation(
                'instagram', reel.get('platform_media_id'), reel.get('published_at'),
                reel.get('title') or f"Instagram Reel {reel.get('platform_media_id')}",
                reel.get('metrics', {}), reel.get('metrics_observed_at'), cached, reel))
        return Fetch(response.get('source'), response.get('fetched_at'), observations, self.raw)
