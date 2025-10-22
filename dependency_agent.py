# dependency_agent.py (for the yt-dlp experiment)

import os
import sys
import google.generativeai as genai
from agent_logic import DependencyAgent

# --- Configuration for the yt-dlp Experiment ---
AGENT_CONFIG = {
    # 1. Point to the file our YAML workflow will create
    "REQUIREMENTS_FILE": "requirements.txt",
    
    # 2. Implement the "smoke test first, then report on pytest" strategy
    "VALIDATION_CONFIG": {
        "type": "script",
        "smoke_test_script": "validation_smoke_ytdlp.py",
        "pytest_target": "yt_dlp test" # The command to run pytest for yt-dlp
    },
    
    # 3. All other standard settings
    "PRIMARY_REQUIREMENTS_FILE": "primary_requirements.txt", # Can be empty
    "METRICS_OUTPUT_FILE": "metrics_output.txt",
    "MAX_LLM_BACKTRACK_ATTEMPTS": 3,
    "MAX_RUN_PASSES": 5,
    "ACCEPTABLE_FAILURE_THRESHOLD": 0 # For yt-dlp, we expect all core tests to pass.
}

if __name__ == "__main__":
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        sys.exit("Error: GEMINI_API_KEY environment variable not set.")
    
    genai.configure(api_key=GEMINI_API_KEY)
    llm_client = genai.GenerativeModel('gemini-1.5-flash-latest')

    agent = DependencyAgent(config=AGENT_CONFIG, llm_client=llm_client)
    agent.run()