# validation_smoke_ytdlp.py

import sys
import subprocess
import os
import json
from pathlib import Path

# --- Configuration ---
# A short, stable, Creative Commons video is the perfect target.
# "Big Buck Bunny" is a classic choice for this.
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"

# We need to predict the output filename to verify the download.
# yt-dlp creates it from the title and ID.
EXPECTED_FILENAME = "Big Buck Bunny [aqz-KE-bpKQ].mp4"


def run_ytdlp_smoke_test():
    """
    Performs a simple but representative workflow with yt-dlp to validate its
    core functionality. This acts as a fast "smoke test".
    """
    print("--- Starting yt-dlp Smoke Test ---")
    
    video_file = Path(EXPECTED_FILENAME)
    
    try:
        # --- Test 1: The "Simple" Test ---
        # Goal: Can we download a short video?
        # This tests the entire critical path: network access, page parsing,
        # format selection, and video downloading.
        print("Running Basic Test: Download a short video...")
        
        # We use `-f b` to select the best quality, but `-S res:360` could be used
        # to force a smaller download if speed is critical.
        simple_test_command = [
            sys.executable,  # Use the same python that is running this script
            "-m", "yt_dlp",
            "-f", "b", # Best quality video and audio
            "--no-warnings",
            TEST_VIDEO_URL,
            "-o", EXPECTED_FILENAME # Force a predictable output filename
        ]
        
        subprocess.run(simple_test_command, check=True, capture_output=True)

        # Verify that the file was actually created and is not empty.
        assert video_file.exists(), f"Basic Test Failed: Expected file '{video_file}' was not created."
        assert video_file.stat().st_size > 100_000, f"Basic Test Failed: File '{video_file}' is suspiciously small."
        
        print("Basic Test PASSED.")

        # --- Test 2: The "Complex" Test ---
        # Goal: Can we extract metadata without downloading?
        # This tests the page parsing and information extraction logic, which is
        # a separate and equally important part of the application. It's also very fast.
        print("\nRunning Complex Test: Fetch and verify video metadata...")

        complex_test_command = [
            sys.executable,
            "-m", "yt_dlp",
            "--dump-json",
            TEST_VIDEO_URL
        ]
        
        # We run the command and capture its standard output.
        result = subprocess.run(complex_test_command, check=True, capture_output=True, text=True)
        metadata = json.loads(result.stdout)
        
        # Verify the complex operation: Does the extracted data look correct?
        assert metadata.get("id") == "aqz-KE-bpKQ", "Complex Test Failed: Video ID in metadata is incorrect."
        assert "Big Buck Bunny" in metadata.get("title", ""), "Complex Test Failed: Video title in metadata is incorrect."

        print("Complex Test PASSED.")
        
        # --- If all tests pass ---
        print("\n--- yt-dlp Smoke Test: ALL TESTS PASSED ---")
        return 0 # Return success code

    except subprocess.CalledProcessError as e:
        print("\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"A command failed with exit code {e.returncode}", file=sys.stderr)
        print(f"STDOUT:\n{e.stdout}", file=sys.stderr)
        print(f"STDERR:\n{e.stderr}", file=sys.stderr)
        return 1 # Return failure code
        
    except Exception as e:
        print(f"\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"An unexpected error occurred: {type(e).__name__} - {e}", file=sys.stderr)
        return 1 # Return failure code
        
    finally:
        # --- Cleanup ---
        # Always make sure the downloaded video file is deleted after the test.
        if video_file.exists():
            print(f"\nCleaning up downloaded file: {video_file}")
            video_file.unlink()


if __name__ == "__main__":
    exit_code = run_ytdlp_smoke_test()
    sys.exit(exit_code)