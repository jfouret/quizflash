"""Retry behaviour of the shared upstream helper: 429 and 5xx get another chance."""

import threading
import time
from collections.abc import Callable

import httpx
import pytest

from app import retry
from app.retry import UpstreamGate, send_with_retries


def _call(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[httpx.Response, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    with httpx.Client(transport=httpx.MockTransport(recording)) as client:
        request = client.build_request("POST", "https://up.test/v1/audio", json={"hello": True})
        response = send_with_retries(client, request)
    return response, requests


def test_a_429_is_retried_and_the_next_response_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retry, "RETRY_DELAYS_SECONDS", (0.0,))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"ok": True})

    response, requests = _call(handler)

    assert response.status_code == 200
    assert calls == 2
    assert len(requests) == 2


def test_the_last_attempt_is_returned_so_the_caller_raises_its_own_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retry, "RETRY_DELAYS_SECONDS", (0.0, 0.0))
    response, requests = _call(lambda request: httpx.Response(500, json={"error": "boom"}))

    assert response.status_code == 500
    assert len(requests) == 3


def test_a_client_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry, "RETRY_DELAYS_SECONDS", (0.0, 0.0))
    response, requests = _call(lambda request: httpx.Response(400, json={"error": "bad input"}))

    assert response.status_code == 400
    assert len(requests) == 1


def test_waits_escalate_and_follow_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(retry, "RETRY_DELAYS_SECONDS", (1.0, 3.0))
    monkeypatch.setattr(time, "sleep", waits.append)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        if len(seen) == 1:
            return httpx.Response(503, headers={"Retry-After": "5"})
        return httpx.Response(503)

    response, _ = _call(handler)

    assert response.status_code == 503
    assert len(seen) == 3
    assert waits == [5.0, 3.0]


def test_a_huge_retry_after_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(retry, "RETRY_DELAYS_SECONDS", (1.0,))
    monkeypatch.setattr(time, "sleep", waits.append)

    response, _ = _call(lambda request: httpx.Response(429, headers={"Retry-After": "600"}))

    assert response.status_code == 429
    assert waits == [retry.MAX_RETRY_AFTER_SECONDS]


def test_a_transport_error_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry, "RETRY_DELAYS_SECONDS", (0.0,))
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        if len(seen) == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json={"ok": True})

    response, _ = _call(handler)

    assert response.status_code == 200
    assert len(seen) == 2


def test_every_failed_attempt_raises_the_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retry, "RETRY_DELAYS_SECONDS", (0.0,))
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    with pytest.raises(httpx.ConnectError):
        _call(handler)


def test_a_streamed_audio_answer_is_retried_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry, "RETRY_DELAYS_SECONDS", (0.0,))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, content=b'{"error": "rate limited"}')
        return httpx.Response(200, content=b"AUDIO", headers={"Content-Type": "audio/mpeg"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        request = client.build_request("POST", "https://up.test/v1/audio/speech", json={})
        response = send_with_retries(client, request, stream=True)
        assert response.status_code == 200
        assert b"".join(response.iter_bytes()) == b"AUDIO"
        response.close()

    assert calls == 2


def test_the_gate_spaces_the_start_of_each_call() -> None:
    slept: list[float] = []
    now = [0.0]

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    gate = UpstreamGate(2.0, clock=clock, sleep=sleep)

    with gate.slot():
        now[0] += 1.0  # the call itself takes a second
    with gate.slot():
        pass

    assert slept == [1.0]


def test_the_gate_never_runs_two_calls_at_once() -> None:
    gate = UpstreamGate(0.0)
    active = 0
    peak = 0

    def worker() -> None:
        nonlocal active, peak
        with gate.slot():
            active += 1
            peak = max(peak, active)
            time.sleep(0.01)
            active -= 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak == 1
