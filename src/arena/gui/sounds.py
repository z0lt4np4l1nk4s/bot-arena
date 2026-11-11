"""Short sound effects, synthesised in code and played without blocking.

There are no audio files: each sound is built from tones and noise with
``wave`` and ``struct`` the first time it is needed. How sounds reach the
speakers depends on the system, so it is hidden behind the
:class:`SoundPlayer` protocol and :func:`choose_player` picks one (a
Factory): ``winsound`` on Windows, the ``aplay`` or ``paplay`` command
elsewhere, or silence. Sound is a nicety; if it fails it is switched off
quietly.
"""

import hashlib
import io
import math
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
import weakref
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Final, Protocol

from arena.gui.effects import Effect, EffectKind
from arena.utilities.decorators import memoize
from arena.utilities.logger import get_logger

SAMPLE_RATE: Final = 22050
MAXIMUM_AMPLITUDE: Final = 32767
# Each sound is mixed at this volume so a turn with several effects
# does not clip too much.
VOLUME: Final = 0.45

logger: Final = get_logger("gui")


def _tone(  # noqa: PLR0913 - every argument shapes the sound
    start_hertz: float,
    end_hertz: float,
    seconds: float,
    *,
    noise: float = 0.0,
    decay: float = 6.0,
    seed: int = 0,
) -> list[float]:
    """A sine sweep with an optional noise share and a fading envelope."""
    count = int(seconds * SAMPLE_RATE)
    generator = random.Random(seed)
    samples: list[float] = []
    phase = 0.0
    for index in range(count):
        progress = index / count
        hertz = start_hertz + (end_hertz - start_hertz) * progress
        phase += 2 * math.pi * hertz / SAMPLE_RATE
        tone = math.sin(phase) * (1 - noise)
        hiss = generator.uniform(-1, 1) * noise
        samples.append((tone + hiss) * math.exp(-decay * progress))
    return samples


def _silence(seconds: float) -> list[float]:
    """Nothing, for ``seconds``."""
    return [0.0] * int(seconds * SAMPLE_RATE)


def _add(first: Sequence[float], second: Sequence[float]) -> list[float]:
    """Two sounds played at the same time."""
    length = max(len(first), len(second))
    return [
        (first[index] if index < len(first) else 0.0)
        + (second[index] if index < len(second) else 0.0)
        for index in range(length)
    ]


@memoize
def _samples(kind: EffectKind) -> tuple[float, ...]:
    """The samples (between -1 and 1) of the sound for ``kind``."""
    if kind is EffectKind.SHOT:
        sound = _tone(1400, 300, 0.18, noise=0.35, decay=5)
    elif kind is EffectKind.HIT:
        sound = _tone(170, 55, 0.28, noise=0.25, decay=4, seed=1)
    elif kind is EffectKind.TRAP_PLACED:
        click = _tone(950, 900, 0.035, decay=3)
        sound = [*click, *_silence(0.05), *_tone(1250, 1200, 0.035, decay=3)]
    elif kind is EffectKind.TRAP_TRIGGERED:
        ring = _add(_tone(520, 500, 0.3, decay=7), _tone(1370, 1340, 0.3))
        sound = _add(_tone(300, 200, 0.06, noise=0.9, seed=2), ring)
    else:
        sound = [
            *_tone(660, 660, 0.1, decay=2),
            *_tone(880, 880, 0.1, decay=2),
            *_tone(1320, 1320, 0.14, decay=4),
        ]
    return tuple(sound)


def _encode(samples: Sequence[float]) -> bytes:
    """A complete mono 16-bit WAV file with ``samples``."""
    frames = struct.pack(
        f"<{len(samples)}h",
        *(
            round(max(-1.0, min(1.0, sample * VOLUME)) * MAXIMUM_AMPLITUDE)
            for sample in samples
        ),
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames)
    return buffer.getvalue()


def synthesize(kind: EffectKind) -> bytes:
    """The WAV file of the sound for one kind of effect."""
    return mix([kind])


def mix(kinds: Iterable[EffectKind]) -> bytes:
    """One WAV file in which the sounds of all ``kinds`` play together."""
    combined: list[float] = []
    for kind in kinds:
        combined = _add(combined, _samples(kind))
    return _encode(combined)


class SoundPlayer(Protocol):
    """Plays a WAV file held in memory; must return at once."""

    def play(self, sound: bytes) -> None:
        """Start playing ``sound`` and return without waiting."""


class _SoundFiles:
    """Writes each distinct sound once to a temporary folder.

    Neither ``winsound`` (asynchronously) nor the commands can play from
    memory, so they get a file path.
    """

    def __init__(self) -> None:
        self._folder: Path | None = None

    def path_for(self, sound: bytes) -> Path:
        """The path of a file that holds ``sound``."""
        if self._folder is None:
            self._folder = Path(tempfile.mkdtemp(prefix="bot-arena-"))
            # Removed when this object is collected or the program ends.
            weakref.finalize(
                self, shutil.rmtree, self._folder, ignore_errors=True
            )
        name = hashlib.sha256(sound).hexdigest()[:16]
        path = self._folder / f"{name}.wav"
        if not path.exists():
            path.write_bytes(sound)
        return path


class WindowsSoundPlayer:
    """Plays sounds with the standard ``winsound`` module."""

    def __init__(self) -> None:
        """Create the player; files are written on first use."""
        self._files = _SoundFiles()

    def play(self, sound: bytes) -> None:
        """Start the sound; a new sound cuts off the previous one."""
        if sys.platform == "win32":
            import winsound  # noqa: PLC0415 - exists only on Windows

            winsound.PlaySound(
                str(self._files.path_for(sound)),
                winsound.SND_FILENAME
                | winsound.SND_ASYNC
                | winsound.SND_NODEFAULT,
            )


class CommandSoundPlayer:
    """Plays sounds by starting a command such as ``aplay``."""

    def __init__(self, command: Sequence[str]) -> None:
        """Create the player.

        Args:
            command: The program and its options; the file is appended.
        """
        self.command = tuple(command)
        self._files = _SoundFiles()
        self._running: list[subprocess.Popen[bytes]] = []

    def play(self, sound: bytes) -> None:
        """Start the command in the background.

        Raises:
            OSError: If an earlier run of the command failed (e.g. there is
                no sound card), so the caller can switch sound off.
        """
        still_running = []
        for process in self._running:
            code = process.poll()
            if code is None:
                still_running.append(process)
            elif code != 0:
                message = f"{self.command[0]} failed with exit code {code}"
                raise OSError(message)
        self._running = still_running
        path = self._files.path_for(sound)
        self._running.append(
            # A fixed command chosen at start-up and a file we wrote.
            subprocess.Popen(
                [*self.command, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )


class SilentSoundPlayer:
    """Plays nothing, for systems without a way to play sound."""

    def play(self, sound: bytes) -> None:
        """Do nothing."""


def choose_player(
    platform: str = sys.platform,
    which: Callable[[str], str | None] = shutil.which,
) -> SoundPlayer:
    """The best way to play sound on this system.

    Args:
        platform: The value of ``sys.platform``.
        which: Finds a program on the path (``shutil.which``).

    Returns:
        A Windows, command or silent player.
    """
    if platform == "win32":
        return WindowsSoundPlayer()
    aplay = which("aplay")
    if aplay is not None:
        return CommandSoundPlayer((aplay, "-q"))
    paplay = which("paplay")
    if paplay is not None:
        return CommandSoundPlayer((paplay,))
    return SilentSoundPlayer()


class SoundEffects:
    """Turns the effects of a turn into one sound, unless muted."""

    def __init__(self, player: SoundPlayer) -> None:
        """Play through ``player`` (injected, so tests can listen)."""
        self.player = player
        self.enabled = True
        self.working = True

    def play(self, effects: Sequence[Effect]) -> None:
        """Play every kind of effect once, mixed together."""
        if not self.enabled or not self.working or not effects:
            return
        kinds = list(dict.fromkeys(effect.kind for effect in effects))
        try:
            self.player.play(mix(kinds))
        except Exception:  # sound is optional; never disturb the window
            logger.warning("sound is switched off", exc_info=True)
            self.working = False
