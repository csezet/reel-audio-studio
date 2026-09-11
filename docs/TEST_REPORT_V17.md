# v17 test report

Environment used for automated verification in this build session:

- Linux execution environment
- FFmpeg 7.1.5 / FFprobe 7.1.5
- Python engine tests (GUI itself was not executed on Windows in this environment)

## Automated unit tests

`python -m unittest discover -s tests -v`

Result: **16/16 passed**.

Coverage includes:

- pause keep-segment calculations
- mastering-chain construction
- limiter ceiling/auto-level settings
- DeepFilter vs FFmpeg denoiser graph behavior
- optional normalization
- Voice+Music DSP safety
- loudnorm first-pass JSON parsing / second-pass parameters
- VAD interval intersection
- VAD probability post-processing
- atomic/cancellable copy
- export suffix normalization
- Windows encoder preference and fallback

## End-to-end FFmpeg test

A synthetic 3.2 s H.264/AAC MP4 was created with a 1.2 s silent region between two tones.

The v17 processor was run with pause shortening + DSP + two-pass loudness normalization. Result:

- input duration: 3.200 s
- processed duration: 2.166154 s
- exported duration: 2.166667 s
- output retained both video and audio
- processing progress reached 100% and was monotonic
- export progress reached 100%
- post-process loudness measurement reported integrated loudness about **−13.97 LUFS** for a −14 LUFS target on the synthetic test clip

This verifies the engine path in the current environment. It does **not** substitute for a Windows 10/11 GUI, codec-driver and installer test matrix.


## v18 regression check

- `compileall`: passed.
- `PYTHONPATH=. pytest -q`: **18 passed**.
- Added source regression tests for the missing `QFont` import and for keeping the primary action clickable for FFmpeg diagnostics.
