"""Tests for the synthesised sounds and how they are played."""

import io
import sys
import unittest
import wave

from applications import wait_for
from arena.gui.effects import Effect, EffectKind
from arena.gui.sounds import (
    SAMPLE_RATE,
    CommandSoundPlayer,
    SilentSoundPlayer,
    SoundEffects,
    WindowsSoundPlayer,
    choose_player,
    synthesize,
)
from arena.model.geometry import Position
from arena.model.side import Side

HIT = Effect(EffectKind.HIT, Side.RED, (Position(1, 1),))
SHOT = Effect(EffectKind.SHOT, Side.BLUE, (Position(2, 1),))


class RecordingPlayer:
    """Remembers every sound it is asked to play."""

    def __init__(self) -> None:
        self.sounds: list[bytes] = []

    def play(self, sound: bytes) -> None:
        self.sounds.append(sound)


class FailingPlayer:
    """A player whose audio device is missing."""

    def __init__(self) -> None:
        self.calls = 0

    def play(self, sound: bytes) -> None:
        self.calls += 1
        message = "no audio device"
        raise OSError(message)


def read_wav(sound: bytes) -> wave.Wave_read:
    """Open a WAV file held in memory."""
    return wave.open(io.BytesIO(sound), "rb")


class SynthesizeTest(unittest.TestCase):
    def test_every_effect_has_a_valid_wav(self) -> None:
        for kind in EffectKind:
            with self.subTest(kind=kind), read_wav(synthesize(kind)) as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), SAMPLE_RATE)
                self.assertGreater(wav.getnframes(), 0)
                self.assertLess(wav.getnframes(), 0.4 * SAMPLE_RATE)

    def test_sounds_are_different(self) -> None:
        sounds = {synthesize(kind) for kind in EffectKind}
        self.assertEqual(len(sounds), len(EffectKind))


class ChoosePlayerTest(unittest.TestCase):
    def test_choose_player_on_windows(self) -> None:
        player = choose_player("win32", lambda _name: None)
        self.assertIsInstance(player, WindowsSoundPlayer)

    def test_choose_player_uses_aplay_when_present(self) -> None:
        def which(name: str) -> str | None:
            return "/usr/bin/aplay" if name == "aplay" else None

        player = choose_player("linux", which)
        assert isinstance(player, CommandSoundPlayer)
        self.assertEqual(player.command, ("/usr/bin/aplay", "-q"))

    def test_choose_player_uses_paplay_without_aplay(self) -> None:
        def which(name: str) -> str | None:
            return "/usr/bin/paplay" if name == "paplay" else None

        player = choose_player("linux", which)
        assert isinstance(player, CommandSoundPlayer)
        self.assertEqual(player.command, ("/usr/bin/paplay",))

    def test_choose_player_falls_back_to_silent(self) -> None:
        player = choose_player("linux", lambda _name: None)
        self.assertIsInstance(player, SilentSoundPlayer)


class SoundEffectsTest(unittest.TestCase):
    def test_effects_play_one_sound(self) -> None:
        player = RecordingPlayer()
        SoundEffects(player).play([HIT])
        self.assertEqual(len(player.sounds), 1)

    def test_turn_sounds_are_mixed_into_one(self) -> None:
        player = RecordingPlayer()
        SoundEffects(player).play([SHOT, HIT, HIT])
        self.assertEqual(len(player.sounds), 1)
        self.assertNotEqual(player.sounds[0], synthesize(EffectKind.SHOT))
        self.assertNotEqual(player.sounds[0], synthesize(EffectKind.HIT))

    def test_no_effects_play_nothing(self) -> None:
        player = RecordingPlayer()
        SoundEffects(player).play([])
        self.assertEqual(player.sounds, [])

    def test_muted_effects_play_nothing(self) -> None:
        player = RecordingPlayer()
        effects = SoundEffects(player)
        effects.enabled = False
        effects.play([HIT])
        self.assertEqual(player.sounds, [])

    def test_failing_player_is_disabled_silently(self) -> None:
        player = FailingPlayer()
        effects = SoundEffects(player)
        with self.assertLogs("arena.gui", "WARNING"):
            effects.play([HIT])
        effects.play([SHOT])
        self.assertEqual(player.calls, 1)

    def test_failing_sound_command_switches_sound_off(self) -> None:
        failing = (sys.executable, "-c", "raise SystemExit(3)")
        effects = SoundEffects(CommandSoundPlayer(failing))
        with self.assertLogs("arena.gui", "WARNING"):
            switched_off = wait_for(
                lambda: not effects.working,
                10,
                lambda: effects.play([HIT]),
            )
        self.assertTrue(switched_off)


if __name__ == "__main__":
    unittest.main()
