"""Quick test harness for the EQ engine using synthetic audio."""
from __future__ import annotations

import argparse

import numpy as np

from equaliser.dsp import EQBand, EQEngine, signals


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline EQ engine smoke test")
    parser.add_argument("--freq", type=float, default=1000.0, help="Test sine frequency in Hz")
    parser.add_argument("--gain", type=float, default=6.0, help="Gain applied to parametric band")
    parser.add_argument("--q", type=float, default=1.5, help="Q factor for the band")
    parser.add_argument("--duration", type=float, default=2.0, help="Seconds of audio to process")
    parser.add_argument("--sample-rate", type=float, default=48000.0, help="Sample rate in Hz")
    args = parser.parse_args()

    engine = EQEngine(sample_rate=args.sample_rate)
    engine.set_bands([EQBand(frequency=args.freq, gain_db=args.gain, q=args.q)])

    test_signal = signals.sine_wave(args.freq, args.sample_rate, args.duration)
    processed = np.zeros_like(test_signal)

    block_size = 1024
    for i in range(0, len(test_signal), block_size):
        block = test_signal[i : i + block_size]
        processed[i : i + len(block)] = engine.process_block(block)

    print("Input level (dBFS):", engine.meter.input_dbfs)
    print("Output level (dBFS):", engine.meter.output_dbfs)


if __name__ == "__main__":
    main()
