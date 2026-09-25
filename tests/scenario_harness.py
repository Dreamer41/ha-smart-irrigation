"""Time-compressed harness for intent-level scenario tests.

The unit tests elsewhere check each gate in isolation ("was the cycle
skipped?"). These scenario tests check what a cycle actually DID: how many
minutes the valve was really open, split into how many pulses, with what
soak gaps -- and therefore how many mm of water went on -- so they can be
compared against what the model says the plant should get.

How it works: the controller only waits in two ways -- asyncio.wait_for()
(a valve-open pulse, or the 45s pump-power wait) and asyncio.sleep() (soak
gaps, pump preamble/postamble). CompressedTime swaps the controller
module's `asyncio` for a proxy whose wait_for/sleep record the requested
duration as SIMULATED time and return almost instantly. Everything else
(Lock, Event, TimeoutError, ...) is the real asyncio.
"""
from __future__ import annotations

import asyncio
import types
from dataclasses import dataclass, field

from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow.const import PUMP_POWER_WAIT_TIMEOUT_SECONDS

_real_wait_for = asyncio.wait_for
_real_sleep = asyncio.sleep


@dataclass
class Pulse:
    valve: str
    minutes: float
    valve_state_during: str


@dataclass
class CompressedTime:
    hass: object
    valve_entities: list[str]
    pulses: list[Pulse] = field(default_factory=list)
    sleeps_seconds: list[float] = field(default_factory=list)
    # Optional async hook called at the start of every valve-open pulse with
    # the 0-based index of that pulse -- lets a test inject an event (abort,
    # a second trigger, a sensor change) at an exact point mid-cycle.
    on_pulse: object = None

    def install(self, monkeypatch) -> "CompressedTime":
        proxy = types.SimpleNamespace(**{k: getattr(asyncio, k) for k in dir(asyncio) if not k.startswith("__")})
        proxy.wait_for = self._wait_for
        proxy.sleep = self._sleep
        monkeypatch.setattr(controller_module, "asyncio", proxy)
        return self

    async def _wait_for(self, aw, timeout=None):
        if timeout is not None and timeout != PUMP_POWER_WAIT_TIMEOUT_SECONDS:
            if self.on_pulse is not None:
                await self.on_pulse(len(self.pulses))
            # A valve-open pulse: record which valve(s) are open right now.
            open_valves = [
                v for v in self.valve_entities if (s := self.hass.states.get(v)) is not None and s.state == "on"
            ]
            for valve in open_valves or ["<none open>"]:
                state = self.hass.states.get(valve)
                self.pulses.append(Pulse(valve, timeout / 60.0, state.state if state else "missing"))
        return await _real_wait_for(aw, timeout=0.001 if timeout is not None else None)

    async def _sleep(self, seconds, *args, **kwargs):
        self.sleeps_seconds.append(seconds)
        await _real_sleep(0)

    # --- convenience -------------------------------------------------
    def pulses_for(self, valve: str) -> list[float]:
        return [p.minutes for p in self.pulses if p.valve == valve]

    def valve_minutes(self, valve: str) -> float:
        return sum(self.pulses_for(valve))

    def reset(self) -> None:
        self.pulses.clear()
        self.sleeps_seconds.clear()
