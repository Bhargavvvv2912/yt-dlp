# validation_smoke_ytdlp.py (The Final, Definitive Version)

import sys
import subprocess
import os
from pathlib import Path

# --- Configuration ---
# Use the stable, direct CDN link to the public domain video.
TEST_VIDEO_URL = "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
EXPECTED_FILENAME = "BigBuckBunny_audio.m4a"

def run_ytdlp_smoke_test():
    """
    Performs a robust, two-stage smoke test to validate yt-dlp's core functionalities:
    1. Information Gathering (Complex Test)
    2. Content Retrieval (Simple Test)
    """
    print("--- Starting yt-dlp Smoke Test ---")
    audio_file = Path(EXPECTED_FILENAME)
    
    try:
        # --- Test 1: The "Complex" Test (Information Gathering) ---
        # Goal: Can yt-dlp correctly parse a video page and list available formats?
        # This is a robust test of the core parsing logic without relying on specific metadata values.
        print("Running Complex Test: List available formats...")

        list_formats_command = [
            sys.executable,
            "-m", "yt_dlp",
            "--list-formats",
            TEST_VIDEO_URL
        ]
        
        result = subprocess.run(
            list_formats_command, check=True, capture_output=True, text=True, timeout=120
        )
        
        # A robust assertion: A correct format list MUST contain these header strings.
        # This is not brittle and will not break if the number of formats changes.
        output = result.stdout
        assert "ID" in output, "Complex Test Failed: 'ID' column is missing from format list."
        assert "EXT" in output, "Complex Test Failed: 'EXT' column is missing from format list."
        assert "RESOLUTION" in output, "Complex Test Failed: 'RESOLUTION' column is missing from format list."

        print("Complex Test PASSED.")

        # --- Test 2: The "Simple" Test (Content Retrieval) ---
        # Goal: Can yt-dlp download a specific format (audio only) to a file?
        # This tests the full download pipeline and is faster than downloading video.
        print("\nRunning Simple Test: Download audio-only format...")
        
        download_command = [
            sys.executable,
            "-m", "yt_dlp",
            "--no-warnings",
            "-f", "bestaudio[ext=m4a]", # Request a specific audio format
            TEST_VIDEO_URL,
            "-o", EXPECTED_FILENAME
        ]
        
        subprocess.run(download_command, check=True, capture_output=True, timeout=300)

        assert audio_file.exists(), f"Simple Test Failed: Expected file '{audio_file}' was not created."
        assert audio_file.stat().st_size > 500_000, f"Simple Test Failed: Audio file '{audio_file}' is suspiciously small."
        
        print("Simple Test PASSED.")
        
        print("\n--- yt-dlp Smoke Test: ALL TESTS PASSED ---")
        return 0

    except subprocess.CalledProcessError as e:
        print("\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"A command failed with exit code {e.returncode}", file=sys.stderr)
        print(f"STDOUT:\n{e.stdout.decode('utf-8', 'ignore')}", file=sys.stderr)
        print(f"STDERR:\n{e.stderr.decode('utf-8', 'ignore')}", file=sys.stderr)
        return 1
        
    except Exception as e:
        print(f"\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"An unexpected error occurred in the smoke test script: {type(e).__name__} - {e}", file=sys.stderr)
        return 1
        
    finally:
        if audio_file.exists():
            print(f"\nCleaning up downloaded file: {audio_file}")
            audio_file.unlink()

if __name__ == "__main__":
    sys.exit(run_ytdlp_smoke_test())