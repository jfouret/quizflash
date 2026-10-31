"""Queueing and retries for remote AI calls: providers answer 429 under load."""

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx

logger = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
# shortcut: fixed waits, and only the plain `Retry-After` seconds form; make them
# configurable per step if a provider needs longer or per-endpoint waits.
RETRY_DELAYS_SECONDS: tuple[float, ...] = (2.0, 5.0, 15.0)
MAX_RETRY_AFTER_SECONDS = 30.0


def _wait_seconds(response: httpx.Response | None, attempt: int) -> float:
    delay = RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS) - 1)]
    if response is not None:
        try:
            retry_after = float(response.headers.get("retry-after", ""))
        except ValueError:
            retry_after = 0.0
        delay = max(delay, min(retry_after, MAX_RETRY_AFTER_SECONDS))
    return delay


def send_with_retries(
    client: httpx.Client, request: httpx.Request, *, stream: bool = False
) -> httpx.Response:
    """Send a request, waiting between attempts on 429/5xx and transport errors.

    The last attempt is returned whatever its status, so the caller keeps its
    usual `raise_for_status()`. A transport error is raised once every attempt
    failed too. With `stream=True` the caller owns the returned response.
    """
    attempts = len(RETRY_DELAYS_SECONDS) + 1
    failed_response: httpx.Response | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(_wait_seconds(failed_response, attempt - 1))
        try:
            response = client.send(request, stream=stream)
        except httpx.TransportError:
            failed_response = None
            if attempt == attempts - 1:
                raise
            continue
        if response.status_code not in RETRY_STATUSES or attempt == attempts - 1:
            return response
        logger.warning("Upstream answered %s for %s; retrying", response.status_code, request.url)
        # Drain the body before the wait, so the connection is free for the retry.
        response.read()
        failed_response = response
    raise AssertionError("unreachable")


class UpstreamGate:
    """One call at a time per step, spaced by a minimum interval.

    Batch study fires several calls of the same step at once (a voice answer per
    card, one speech request per explanation), which is what a provider answers
    with 429. Calls queue here instead: the interval spaces their starts, and the
    next call waits for the running one, retries included.
    """

    def __init__(
        self,
        min_interval_seconds: float = 0.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_start = 0.0

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._lock:
            now = self._clock()
            delay = self._next_start - now
            if delay > 0:
                self._sleep(delay)
                now = self._clock()
            self._next_start = now + self.min_interval_seconds
            yield
