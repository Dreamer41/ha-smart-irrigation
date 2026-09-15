# Testing this integration without touching real hardware

This repo has two independent layers of automated testing, plus a manual
sandbox for clicking around a real Home Assistant UI. None of them touch
your production Home Assistant or the real valve.

## 1. Pure logic tests (no Home Assistant needed)

`tests/test_calculations.py` and `tests/test_rain_tracker.py` test the math
directly -- deep soak sizing, routine watering sizing, rain-window tracking,
drydown timing -- with plain Python, no Home Assistant installed at all.

```
pip install pytest
pytest tests/test_calculations.py tests/test_rain_tracker.py -v
```

## 2. Full integration tests (real Home Assistant core, simulated)

`tests/test_smoke_setup.py` boots an actual Home Assistant core process in
memory, loads this integration into it exactly like your real HA would,
feeds it fake sensor states, and checks that every entity, service, and
piece of internal state comes out right. This is what caught the
sensor/binary_sensor crash bug.

Setup (one-time):

```
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

# Linux/macOS only -- see note in requirements-test.txt:
pip install "setuptools<66" wheel

pip install -r requirements-test.txt
```

Run:

```
pytest tests/ -v
```

## 3. Manual sandbox: a real HA instance you can click around in

See `sandbox/README.md`. This runs actual Home Assistant in Docker on your
own machine, with fake/simulated valve, pump, rain, and temperature sensors
you control from sliders in the HA UI -- so you can add the integration,
push its buttons, and watch it behave in a real dashboard, with zero
connection to your production HA or real hardware.
