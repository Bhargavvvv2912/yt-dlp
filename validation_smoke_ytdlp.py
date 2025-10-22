# validation_smoke_ytdlp.py (The Final, Simple, Correct Version)

import sys
import subprocess
from pathlib import Path

# --- Configuration ---
# A direct, permanent, CDN-hosted link to a small MP4 file.
TEST_VIDEO_URL = "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
EXPECTED_FILENAME = "BigBuckBunny.mp4"

def run_ytdlp_smoke_test():
    """
    Performs one simple, robust test: can yt-dlp download this one file?
    This is the core "User Loop" functionality.
    """
    print("--- Starting yt-dlp Smoke Test ---")
    video_file = Path(EXPECTED_FILENAME)
    
    try:
        # --- THE ONE AND ONLY TEST: THE DOWNLOAD ---
        print("Running smoke test: Can we download a video from a stable CDN?")
        
        # We give the simplest possible command. No format selection. Just download the file.
        command = [
            sys.executable,
            "-m", "yt_dlp",
            "--no-warnings",
            TEST_VIDEO_URL,
            "-o", EXPECTED_FILENAME
        ]
        
        # Use a timeout to prevent hangs.
        subprocess.run(command, check=True, capture_output=True, timeout=300)

        # The only validation we need: did the file download and is it a reasonable size?
        assert video_file.exists(), f"Smoke Test Failed: Expected file '{video_file}' was not created."
        assert video_file.stat().st_size > 1_000_000, f"Smoke Test Failed: File '{video_file}' is suspiciously small."
        
        print("Smoke Test: Download successful and file looks valid.")
        print("\n--- yt-dlp Smoke Test: PASSED ---")
        return 0

    except subprocess.CalledProcessError as e:
        print("\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"yt-dlp command failed with exit code {e.returncode}", file=sys.stderr)
        print(f"STDOUT:\n{e.stdout.decode('utf-8', 'ignore')}", file=sys.stderr)
        print(f"STDERR:\n{e.stderr.decode('utf-8', 'ignore')}", file=sys.stderr)
        return 1
        
    except Exception as e:
        print(f"\n--- yt-dlp Smoke Test: FAILED ---", file=sys.stderr)
        print(f"An unexpected error occurred in the smoke test script: {type(e).__name__} - {e}", file=sys.stderr)
        return 1
        
    finally:
        # Always clean up the downloaded file.
        if video_file.exists():
            print(f"\nCleaning up downloaded file: {video_file}")
            video_file.unlink()

if __name__ == "__main__":
    sys.exit(run_ytdlp_smoke_test())