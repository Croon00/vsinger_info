"""World cup submission checks: bracket shape, pace and per-client limits."""
from collections import deque
from threading import Lock
import time

from app.schemas.worldcup import WorldcupSubmission

CLIENT_RUNS_PER_HOUR = 20
ADDRESS_RUNS_PER_HOUR = 60
MIN_SECONDS_PER_MATCH = 1


class SubmissionRejected(ValueError):
    """Carries a short, public reason code."""


def validate_bracket(submission: WorldcupSubmission) -> tuple[list[str], str]:
    """Return (round-one songs, champion) if the matches form one complete bracket.

    Round r has r/2 matches; each match pairs the winners of two neighbouring matches
    of the previous round, so a tampered or partial bracket is rejected.
    """
    size, matches = submission.size, submission.matches
    if len(matches) != size - 1:
        raise SubmissionRejected('match_count')
    expected, remaining = [], size
    while remaining >= 2:
        expected += [remaining] * (remaining // 2)
        remaining //= 2
    if [match.round for match in matches] != expected:
        raise SubmissionRejected('round_order')
    first_round = [song for match in matches[: size // 2] for song in (match.winner, match.loser)]
    if len(set(first_round)) != size:
        raise SubmissionRejected('duplicate_song')
    alive, position, remaining = first_round, 0, size
    while remaining >= 2:
        round_matches = matches[position : position + remaining // 2]
        for index, match in enumerate(round_matches):
            if {match.winner, match.loser} != {alive[2 * index], alive[2 * index + 1]}:
                raise SubmissionRejected('pairing')
        alive = [match.winner for match in round_matches]
        position += remaining // 2
        remaining //= 2
    return first_round, alive[0]


def check_pace(submission: WorldcupSubmission) -> None:
    if submission.duration_seconds < (submission.size - 1) * MIN_SECONDS_PER_MATCH:
        raise SubmissionRejected('too_fast')


class AddressLimiter:
    """In-process sliding window per forwarded address; the address is never stored."""

    def __init__(self, limit: int = ADDRESS_RUNS_PER_HOUR, window: float = 3600):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque[float]] = {}
        self.lock = Lock()

    def allow(self, address: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self.lock:
            hits = self.hits.setdefault(address, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self.hits) > 10000:  # bound memory under address churn
                self.hits = {key: value for key, value in self.hits.items() if value}
            return True


address_limiter = AddressLimiter()
