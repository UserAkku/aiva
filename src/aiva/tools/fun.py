"""Fun skills that need real randomness (LLMs are bad at being random)."""

from __future__ import annotations

import secrets

from ..brain.toolsets import ToolRegistry

_rng = secrets.SystemRandom()


def register(reg: ToolRegistry) -> None:
    @reg.tool("fun")
    def flip_coin() -> str:
        """Toss a coin."""
        return _rng.choice(["heads", "tails"])

    @reg.tool("fun")
    def roll_dice(count: int = 1, sides: int = 6) -> str:
        """Roll dice.

        Args:
            count: Number of dice (1-10).
            sides: Sides per die.
        """
        rolls = [_rng.randint(1, max(2, sides)) for _ in range(max(1, min(count, 10)))]
        return f"rolled {rolls}, total {sum(rolls)}"

    @reg.tool("fun")
    def pick_random(options: list[str]) -> str:
        """Pick one option at random (who goes first, what to eat, …).

        Args:
            options: The choices.
        """
        return _rng.choice(options) if options else "no options given"

    @reg.tool("fun")
    def random_number(minimum: int = 1, maximum: int = 100) -> str:
        """A random whole number in a range (for guessing games etc.).

        Args:
            minimum: Lowest value.
            maximum: Highest value.
        """
        lo, hi = sorted((minimum, maximum))
        return str(_rng.randint(lo, hi))
