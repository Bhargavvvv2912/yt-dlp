# validation_smoke_ytdlp.py

import sys
import subprocess
import os
import json
from pathlib import Path

# --- THIS IS THE FIX ---
# We are switching from a flaky YouTube URL to a stable, permanent, public domain video
# from the Internet Archive. This URL will never have a CAPTCHA.
TEST_VIDEO_URL = "https://archive.org/details/trip_to_the_moon_1902"

# The new predictable filename
EXPECTED_FILENAME = "A Trip to the Moon [trip_to_the_moon_1902].mp4"

def run_ytdlp_smoke_test():
    """
    Performs a simple but representative workflow with yt-dlp to validate its
    core functionality. This acts as a fast "smoke test".
    """
    print("--- Starting yt-dlp Smoke Test ---")
    
    video_file = Path(EXPECTED_FILENAME)
    
    try:
        # --- Test 1: The "Basic" Test (Download) ---
        print("Running Basic Test: Download a short public domain video...")
        
        simple_test_command = [
            sys.executable,
            "-m", "yt_dlp",
            "--no-warnings",
            TEST_VIDEO_URL,
            "-o", EXPECTED_FILENAME
        ]
        
        # Use a timeout to prevent hangs on network issues
        subprocess.run(simple_test_command, check=True, capture_output=True, timeout=300)

        assert video_file.exists(), f"Basic Test Failed: Expected file '{video_file}' was not created."
        assert video_file.stat().st_size > 100_000, f"Basic Test Failed: File '{video_file}' is suspiciously small."
        
        print("Basic Test PASSED.")

        # --- Test 2: The "Complex" Test (Metadata) ---
        print("\nRunning Complex Test: Fetch and verify video metadata...")

        complex_test_command = [
            sys.executable,
            "-m", "yt_dlp",
            "--dump-json",
            TEST_VIDEO_URL
        ]
        
        result = subprocess.run(complex_test_command, check=True, capture_output=True, text=True, timeout=120)
        metadata = json.loads(result.stdout)
        
        assert metadata.get("id") == "trip_to_the_moon_1902", "Complex Test Failed: Video ID in metadata is incorrect."
        assert "A Trip to the Moon" in metadata.get("title", ""), "Complex Test Failed: Video title in metadata is incorrect."

        print("Complex Test PASSED.")
        
        print("\n--- yt-dlp Smoke Test: ALL TESTS PASSED ---")
        return 0

    except subprocess.CalledProcessError as e:
        print("\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"A command failed with exit code {e.returncode}", file=sys.stderr)
        print(f"STDOUT:\n{e.stdout}", file=sys.stderr)
        print(f"STDERR:\n{e.stderr}", file=sys.stderr)
        return 1
        
    except Exception as e:
        print(f"\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"An unexpected error occurred: {type(e).__name__} - {e}", file=sys.stderr)
        return 1
        
    finally:
        if video_file.exists():
            print(f"\nCleaning up downloaded file: {video_file}")
            video_file.unlink()

if __name__ == "__main__":
    sys.exit(run_ytdlp_smoke_test())