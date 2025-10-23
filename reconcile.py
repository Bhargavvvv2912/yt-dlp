# reconcile.py (The Final, Correct, and Clean Version)

from pathlib import Path
import re
import sys

def get_package_name_from_line(line: str) -> str | None:
    """Robustly extracts the package name from a requirements line."""
    match = re.match(r'^(-e\s+)?([a-zA-Z0-9\-_]+)', line.strip())
    return match.group(2) if match else None

def clean_line_for_golden_record(line: str) -> str:
    """
    Takes a full requirements line from pip-compile and returns only the
    'package==version' or '-e ...' part, stripping all markers and comments.
    This is YOUR core, correct logic.
    """
    # The `-e` line is special and must be preserved as-is.
    if line.strip().startswith('-e'):
        return line.strip()
    
    # For all other lines, we take only the part before the first semicolon.
    return line.split(';')[0].strip()

def reconcile_requirements():
    """
    Intelligently reconciles the Golden Record (requirements.txt) with the
    Ideal State (temp-ideal-state.txt), ensuring the Golden Record is always clean.
    """
    golden_record_path = Path("requirements.txt")
    ideal_state_path = Path("temp-ideal-state.txt")

    if not ideal_state_path.exists():
        sys.exit("ERROR: Ideal state file (temp-ideal-state.txt) not found.")

    with open(ideal_state_path, "r") as f:
        ideal_deps_lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    
    # --- THIS IS THE FINAL, UNIFIED LOGIC ---
    
    # If the Golden Record doesn't exist, create it with CLEANED lines.
    if not golden_record_path.exists() or golden_record_path.stat().st_size == 0:
        print("Golden Record (requirements.txt) is missing or empty. Creating a clean version from the ideal state.")
        
        # Apply the cleaning function to EVERY line.
        cleaned_lines = [clean_line_for_golden_record(line) for line in ideal_deps_lines]
        
        with open(golden_record_path, "w") as f:
            f.write("\n".join(sorted(cleaned_lines)))
        print(f"Created a new, clean Golden Record with {len(cleaned_lines)} packages.")
        return

    # For subsequent runs, we also use the cleaning logic.
    with open(golden_record_path, "r") as f:
        golden_package_names = {get_package_name_from_line(line) for line in f if line.strip()}
    
    new_deps_to_add = []
    for ideal_line in ideal_deps_lines:
        ideal_pkg_name = get_package_name_from_line(ideal_line)
        
        if ideal_pkg_name and ideal_pkg_name.lower() not in (name.lower() for name in golden_package_names):
            # YOUR LOGIC: Clean the line BEFORE appending it.
            cleaned_line = clean_line_for_golden_record(ideal_line)
            print(f"New dependency '{ideal_pkg_name}' discovered. Adding cleaned version to Golden Record: '{cleaned_line}'")
            new_deps_to_add.append(cleaned_line)

    if new_deps_to_add:
        print(f"Adding {len(new_deps_to_add)} new, clean dependencies to Golden Record.")
        with open(golden_record_path, "a") as f:
            f.write("\n" + "\n".join(sorted(new_deps_to_add)))
    else:
        print("Golden Record is in sync with pyproject.toml. No new dependencies found.")

if __name__ == "__main__":
    reconcile_requirements()