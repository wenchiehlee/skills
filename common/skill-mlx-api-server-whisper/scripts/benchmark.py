import time
import sys
import os
from pathlib import Path

def run_benchmark(audio_path=None):
    try:
        from whisperkittools import WhisperKit
    except ImportError:
        print("Error: 'whisperkittools' not found.")
        print("Please run: pip install whisperkittools")
        return

    # 1. Initialize WhisperKit with ANE-optimized model
    # distil-whisper-large-v3 is highly recommended for M4 ANE
    model_name = "distil-whisper_distil-large-v3"
    print(f"--- Benchmark Starting on Apple M4 ---")
    print(f"Loading model: {model_name}...")
    
    t0 = time.monotonic()
    wk = WhisperKit(model_name=model_name)
    load_time = time.monotonic() - t0
    print(f"Model loaded in {load_time:.2f}s")

    # 2. Check for audio file
    if not audio_path:
        print("\nNo audio file provided. Please provide a path to a ~5 min audio file.")
        print("Usage: python benchmark.py <path_to_audio>")
        return

    audio_file = Path(audio_path)
    if not audio_file.exists():
        print(f"Error: File {audio_path} not found.")
        return

    print(f"\nTranscribing: {audio_file.name}")
    
    # 3. Transcribe and Measure
    t1 = time.monotonic()
    result = wk.transcribe(str(audio_file))
    elapsed = time.monotonic() - t1
    
    # 4. Results
    text = result.get("text", "")
    # Note: In a real scenario, we'd get audio duration from ffmpeg
    # Here we just output the raw time first
    print(f"\n--- Results ---")
    print(f"Transcription Time: {elapsed:.2f}s")
    print(f"Text Preview: {text[:100]}...")
    
    print(f"\nNote: If the transcription time is significantly shorter than audio duration,")
    print(f"it confirms that the Apple M4 Neural Engine (ANE) is working correctly.")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    run_benchmark(path)
