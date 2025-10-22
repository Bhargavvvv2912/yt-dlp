# validation_smoke_ytdlp.py

import sys
import subprocess
import os
import json
from pathlib import Path

# --- THIS IS THE FINAL FIX ---
# We are using a direct, permanent, CDN-hosted link to a small MP4 file.
# This link is from the official source of the "Big Buck Bunny" open-source movie.
# It requires no complex webpage parsing and is guaranteed to be stable.
TEST_VIDEO_URL = "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"

# The filename will be predictable now.
EXPECTED_FILENAME = "BigBuckBunny.mp4"


def run_ytdlp_smoke_test():
    """
    Performs a simple but representative workflow with yt-dlp to validate its
    core functionality. This acts as a fast "smoke test".
    """
    print("--- Starting yt-dlp Smoke Test ---")
    
    video_file = Path(EXPECTED_FILENAME)
    
    try:
        # --- Test 1: The "Basic" Test (Download) ---
        print("Running Basic Test: Download a short public domain video from a stable CDN...")
        
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
        assert video_file.stat().st_size > 1_000_000, f"Basic Test Failed: File '{video_file}' is suspiciously small." # 1MB
        
        print("Basic Test PASSED.")

        # --- Test 2: The "Complex" Test (Metadata) ---
        # With a direct file link, metadata is simpler, but we can still check it.
        print("\nRunning Complex Test: Fetch and verify media metadata...")

        complex_test_command = [
            sys.executable,
            "-m", "yt_dlp",
            "--dump-json",
            TEST_VIDEO_URL
        ]
        
        result = subprocess.run(complex_test_command, check=True, capture_output=True, text=True, timeout=120)
        metadata = json.loads(result.stdout)
        
        # Verify the complex operation: Does the extracted data look correct?
        assert "BigBuckBunny" in metadata.get("title", ""), "Complex Test Failed: Video title in metadata is incorrect."
        assert metadata.get("duration", 0) > 500, "Complex Test Failed: Video duration seems incorrect." # It's about 10 mins long

        print("Complex Test PASSED.")
        
        print("\n--- yt-dlp Smoke Test: ALL TESTS PASSED ---")
        return 0

    except subprocess.CalledProcessError as e:
        print("\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"A command failed with exit code {e.returncode}", file=sys.stderr)
        # Use .decode() to get a clean string from the byte output
        stdout_str = e.stdout.decode('utf-8', 'ignore')
        stderr_str = e.stderr.decode('utf-8', 'ignore')
        print(f"STDOUT:\n{stdout_str}", file=sys.stderr)
        print(f"STDERR:\n{stderr_str}", file=sys.stderr)
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