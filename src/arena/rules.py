"""Game rules: every number the game depends on, in one validated place.

Each rule is a :class:`Bounded` descriptor, so an invalid value is rejected
the moment it is set, wherever it comes from.
"""

from typing import Final, overload

from arena.errors import RulesError


class Bounded:
    """A descriptor for an integer rule with a default and allowed range.

    >>> class Example:
    ...     speed = Bounded(default=3, minimum=1, maximum=5)
    >>> example = Example()
    >>> example.speed = 9
    Traceback (most recent call last):
    ...
    arena.errors.RulesError: speed must be between 1 and 5, got 9
    """

    def __init__(self, default: int, minimum: int, maximum: int) -> None:
        """Create the descriptor.

        Args:
            default: The value used when none is given.
            minimum: The smallest allowed value (inclusive).
            maximum: The largest allowed value (inclusive).

        Raises:
            RulesError: If the default is not within the range (this also
                rejects a minimum above the maximum).
        """
        if not minimum <= default <= maximum:
            message = (
                f"default {default} is outside the range {minimum}..{maximum}"
            )
            raise RulesError(message)
        self.default = default
        self.minimum = minimum
        self.maximum = maximum
        self.name = ""

    def __set_name__(self, owner: type, name: str) -> None:
        """Remember the attribute name the descriptor is assigned to."""
        self.name = name

    @overload
    def __get__(self, instance: None, owner: type) -> "Bounded": ...

    @overload
    def __get__(self, instance: object, owner: type) -> int: ...

    def __get__(self, instance: object | None, owner: type) -> "Bounded | int":
        """Return the stored value, or the descriptor itself on the class."""
        if instance is None:
            return self
        value: int = instance.__dict__.get(self.name, self.default)
        return value

    def __set__(self, instance: object, value: int) -> None:
        """Validate and store a value.

        Raises:
            RulesError: If the value is not an integer or is out of range.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            message = f"{self.name} must be an integer, got {value!r}"
            raise RulesError(message)
        if not self.minimum <= value <= self.maximum:
            message = (
                f"{self.name} must be between {self.minimum} and "
                f"{self.maximum}, got {value}"
            )
            raise RulesError(message)
        instance.__dict__[self.name] = value


class Rules:
    """The complete, immutable set of game rules.

    Any rule can be overridden by keyword; the rest keep their defaults.
    Once created, the rules cannot be changed:

    >>> Rules().bullet_range = 9
    Traceback (most recent call last):
    ...
    arena.errors.RulesError: rules are frozen, cannot set bullet_range
    """

    # The rules are descriptors, not plain class variables, so they are not
    # annotated with ClassVar: each instance stores its own value.

    _frozen: bool = False

    grid_size = Bounded(default=20, minimum=6, maximum=50)
    wall_percent = Bounded(default=15, minimum=0, maximum=40)
    crystal_pairs = Bounded(default=8, minimum=1, maximum=40)
    carry_capacity = Bounded(default=3, minimum=1, maximum=10)
    bullet_range = Bounded(default=5, minimum=1, maximum=20)
    shoot_cooldown = Bounded(default=5, minimum=0, maximum=50)
    stun_turns = Bounded(default=2, minimum=0, maximum=20)
    traps_per_bot = Bounded(default=3, minimum=0, maximum=10)
    trap_lifetime = Bounded(default=5, minimum=1, maximum=50)
    trap_stuck_turns = Bounded(default=3, minimum=0, maximum=20)
    duel_max_turns = Bounded(default=200, minimum=1, maximum=10_000)
    solo_max_turns = Bounded(default=300, minimum=1, maximum=10_000)
    turn_time_limit_ms = Bounded(default=100, minimum=10, maximum=10_000)
    bot_kill_timeout_ms = Bounded(default=2000, minimum=100, maximum=60_000)

    def __init__(self, **overrides: int) -> None:
        """Create rules from the defaults and the given overrides.

        Args:
            **overrides: Rule names mapped to new values.

        Raises:
            RulesError: If a name is unknown, a value is invalid, or the
                grid size is odd (the map symmetry needs an even size).
        """
        rules = self._rule_descriptors()
        unknown = sorted(set(overrides) - set(rules))
        if unknown:
            message = f"unknown rules: {', '.join(unknown)}"
            raise RulesError(message)
        for name, descriptor in rules.items():
            setattr(self, name, overrides.get(name, descriptor.default))
        if self.grid_size % 2 != 0:
            message = f"grid_size must be even, got {self.grid_size}"
            raise RulesError(message)
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        """Allow setting rules only while the object is being created.

        Raises:
            RulesError: If the rules were already created.
        """
        if self._frozen:
            message = f"rules are frozen, cannot set {name}"
            raise RulesError(message)
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        """Forbid deleting attributes, which could undo the freeze.

        Raises:
            RulesError: Always.
        """
        message = f"rules are frozen, cannot delete {name}"
        raise RulesError(message)

    @classmethod
    def _rule_descriptors(cls) -> dict[str, Bounded]:
        """Find every rule by inspecting the class for descriptors."""
        return {
            name: attribute
            for name, attribute in vars(cls).items()
            if isinstance(attribute, Bounded)
        }


DEFAULT_RULES: Final[Rules] = Rules()
