# reconcile.py (The Final, Correct "Trust but Verify" Version)

from pathlib import Path
import re
import sys

def get_package_name_from_line(line: str) -> str | None:
    """Robustly extracts the package name from a requirements line."""
    # This regex is designed to capture the package name reliably.
    match = re.match(r'^(-e\s+)?([a-zA-Z0-9\-_]+)', line.strip())
    return match.group(2) if match else None

def reconcile_requirements():
    """
    Intelligently reconciles the Golden Record (requirements.txt) with the
    Ideal State (temp-ideal-state.txt) generated from pyproject.toml.
    
    YOUR FINAL, CORRECT LOGIC:
    - If a package is new, its ENTIRE line from the ideal state is copied.
      This preserves crucial constraints like >= or environment markers.
    """
    golden_record_path = Path("requirements.txt")
    ideal_state_path = Path("temp-ideal-state.txt")

    if not ideal_state_path.exists():
        sys.exit("ERROR: Ideal state file not found.")

    with open(ideal_state_path, "r") as f:
        ideal_deps_lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    
    # --- The First Run: We now trust pip-compile completely ---
    if not golden_record_path.exists() or golden_record_path.stat().st_size == 0:
        print("Golden Record not found. Creating a new one directly from the ideal state.")
        # We copy the file exactly. It is now our first Golden Record.
        shutil.copy(ideal_state_path, golden_record_path)
        print(f"Created a new Golden Record with {len(ideal_deps_lines)} packages.")
        return

    # --- Subsequent Runs: The "Trust but Verify" Comparison ---
    with open(golden_record_path, "r") as f:
        golden_package_names = {get_package_name_from_line(line) for line in f if line.strip()}
    
    new_deps_to_add = []
    for ideal_line in ideal_deps_lines:
        ideal_pkg_name = get_package_name_from_line(ideal_line)
        if ideal_pkg_name and ideal_pkg_name not in golden_package_names:
            # YOUR LOGIC: Add the new package with its full, original constraint.
            print(f"New dependency '{ideal_pkg_name}' discovered. Adding its full constraint to Golden Record: '{ideal_line}'")
            new_deps_to_add.append(ideal_line)

    if new_deps_to_add:
        print(f"Adding {len(new_deps_to_add)} new dependencies to Golden Record.")
        with open(golden_record_path, "a") as f:
            f.write("\n" + "\n".join(sorted(new_deps_to_add)))
    else:
        print("Golden Record is in sync. No new dependencies found.")

if __name__ == "__main__":
    # We need `shutil` for the copy operation
    import shutil
    reconcile_requirements()