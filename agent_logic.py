import os
import sys
import venv
from pathlib import Path
import ast
import shutil
import re
import json
from google.api_core.exceptions import ResourceExhausted, NotFound
from pypi_simple import PyPISimple
from packaging.version import parse as parse_version
from agent_utils import start_group, end_group, run_command, validate_changes

class DependencyAgent:
    def __init__(self, config, llm_client):
        self.config = config
        self.llm = llm_client
        self.pypi = PyPISimple()
        self.requirements_path = Path(config["REQUIREMENTS_FILE"])
        self.primary_packages = self._load_primary_packages()
        self.llm_available = True
        self.usage_scores = self._calculate_risk_scores()
        self.exclusions_from_this_run = set()

    def _calculate_risk_scores(self):
        start_group("Analyzing Codebase for Update Risk")
        scores = {}
        project_dir_name = self.config.get("VALIDATION_CONFIG", {}).get("project_dir")
        if project_dir_name and Path(project_dir_name).is_dir():
            repo_dir = Path(project_dir_name)
        else:
            repo_dir = Path('.')

        for py_file in repo_dir.rglob('*.py'):
            if any(part in str(py_file) for part in ['temp_venv', 'final_venv', 'bootstrap_venv']):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                module_name = self._get_package_name_from_spec(alias.name.split('.')[0])
                                scores[module_name] = scores.get(module_name, 0) + 1
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            module_name = self._get_package_name_from_spec(node.module.split('.')[0])
                            scores[module_name] = scores.get(module_name, 0) + 1
            except Exception:
                continue
        
        normalized_scores = {name.replace('_', '-'): score for name, score in scores.items()}
        print("Usage scores calculated.")
        end_group()
        return normalized_scores

    def _get_package_name_from_spec(self, spec_line):
        match = re.match(r'([a-zA-Z0-9\-_]+)', spec_line)
        return match.group(1) if match else None

    def _load_primary_packages(self):
        primary_path = Path(self.config["PRIMARY_REQUIREMENTS_FILE"])
        if not primary_path.exists(): return set()
        with open(primary_path, "r") as f:
            return {self._get_package_name_from_spec(line.strip()) for line in f if line.strip() and not line.startswith('#')}

    def _get_requirements_state(self):
        if not self.requirements_path.exists():
            sys.exit(f"CRITICAL ERROR: Requirements file not found at {self.requirements_path}")

        with open(self.requirements_path, "r") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        
        if not lines:
            return True, []

        pinned_pattern = re.compile(r'^[a-zA-Z0-9\-_\[\]\.]+==.+$')

        def is_unpinned(line):
            if line.startswith('-e'): return False
            if pinned_pattern.match(line): return False
            return True

        is_fully_pinned = not any(is_unpinned(line) for line in lines)
        return is_fully_pinned, lines

    def _bootstrap_unpinned_requirements(self):
        start_group("BOOTSTRAP: Establishing a Stable Baseline")
        print("Unpinned requirements detected. Creating and validating a stable baseline...")
        venv_dir = Path("./bootstrap_venv")
        if venv_dir.exists(): shutil.rmtree(venv_dir)
        venv.create(venv_dir, with_pip=True)
        python_executable = str((venv_dir / "bin" / "python").resolve())
        
        print(f"\n--- Step 1: Installing from requirements file: {self.requirements_path} ---")
        _, stderr, returncode = run_command([python_executable, "-m", "pip", "install", "-r", str(self.requirements_path)])
        
        if returncode != 0:
            print(f"CRITICAL ERROR: Failed to install initial dependencies. Log follows:\n{stderr}")
            sys.exit("Bootstrap installation failed.")
        print("Initial installation successful.")

        print("\n--- Step 2: Validating the new baseline environment ---")
        success, metrics, validation_output = validate_changes(python_executable, self.config, group_title="Running Validation on New Baseline")
        if not success:
            print("View Initial Baseline Failure Log", validation_output)
            sys.exit("CRITICAL ERROR: Initial dependencies passed installation but failed validation.")
        print("Validation of new baseline PASSED.")

        print("\n--- Step 3: Freezing the validated environment ---")
        installed_packages, _, _ = run_command([python_executable, "-m", "pip", "freeze"])
        final_packages = self._prune_pip_freeze(installed_packages)
        with open(self.requirements_path, "w") as f: f.write(final_packages)
        
        start_group("View new requirements.txt content"); print(final_packages); end_group()
        if metrics and "not available" not in metrics:
            print(f"\n{'='*70}\n=== BOOTSTRAP SUCCESSFUL... ===\n" + "\n".join([f"  {line}" for line in metrics.split('\n')]) + f"\n{'='*70}\n")
            with open(self.config["METRICS_OUTPUT_FILE"], "w") as f: f.write(metrics)
        end_group()

    def run(self):
        if os.path.exists(self.config["METRICS_OUTPUT_FILE"]): os.remove(self.config["METRICS_OUTPUT_FILE"])
        
        is_pinned, _ = self._get_requirements_state()
        if not is_pinned:
            self._bootstrap_unpinned_requirements()
            is_pinned, _ = self._get_requirements_state()
            if not is_pinned:
                 sys.exit("CRITICAL: Bootstrap process failed to produce a fully pinned requirements file.")

        dynamic_constraints = []
        final_successful_updates = {}
        final_failed_updates = {}
        pass_num = 0
        self._run_final_health_check()
        while pass_num < self.config["MAX_RUN_PASSES"]:
            pass_num += 1
            start_group(f"UPDATE PASS {pass_num}/{self.config['MAX_RUN_PASSES']}")
            
            pass_baseline_reqs_path = Path(f"./pass_{pass_num}_baseline_reqs.txt")
            shutil.copy(self.requirements_path, pass_baseline_reqs_path)
            
            packages_to_update = []
            with open(pass_baseline_reqs_path, 'r') as f:
                lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            
            for line in lines:
                if '==' not in line: continue
                package_part = line.split(';')[0].strip()
                
                # 2. Now, we are left with a clean 'package==version' string, which is safe to split.
                parts = package_part.split('==')
                if len(parts) != 2: continue # Safety check for malformed lines like '-e .'

                package = self._get_package_name_from_spec(parts[0].strip())
                current_version = parts[1].strip()
                # --- END OF YOUR FIX ---

                latest_version = self.get_latest_version(package)
                if latest_version and parse_version(latest_version) > parse_version(current_version):
                    packages_to_update.append((package, current_version, latest_version))
            if not packages_to_update:
                if pass_num == 1:
                    print("\nInitial baseline is already fully up-to-date. The upstream resolver found the optimal versions.")
                    print("Running a final health check on the baseline for confirmation.")
                    self._run_final_health_check()
                else:
                    print("\nNo further updates are available after the previous pass. The system has successfully converged.")
                
                end_group()
                if pass_baseline_reqs_path.exists(): pass_baseline_reqs_path.unlink()
                break

            packages_to_update.sort(key=lambda p: self._calculate_update_risk(p[0], p[1], p[2]), reverse=True)
            print("\nPrioritized Update Plan for this Pass:")
            total_updates_in_plan = len(packages_to_update)
            for i, (pkg, cur_ver, target_ver) in enumerate(packages_to_update):
                score = self._calculate_update_risk(pkg, cur_ver, target_ver)
                print(f"  {i+1}/{total_updates_in_plan}: {pkg} (Risk: {score:.2f}) -> {target_ver}")
            
            changed_packages_this_pass = set()
            pass_successful_updates = {}

            for i, (package, current_ver, target_ver) in enumerate(packages_to_update):
                print(f"\n" + "-"*80); print(f"PULSE: [PASS {pass_num} | ATTEMPT {i+1}/{total_updates_in_plan}] Processing '{package}'"); print(f"PULSE: Changed packages this pass so far: {changed_packages_this_pass}"); print("-"*80)
                
                success, reason, _ = self.attempt_update_with_healing(
                    package, current_ver, target_ver, dynamic_constraints, pass_baseline_reqs_path, changed_packages_this_pass
                )
                
                if success:
                    final_successful_updates[package] = (target_ver, reason)
                    pass_successful_updates[package] = reason
                    if current_ver != reason:
                        changed_packages_this_pass.add(package)
                else:
                    final_failed_updates[package] = (target_ver, reason)
            
            if changed_packages_this_pass:
                self._apply_pass_updates(pass_successful_updates, pass_baseline_reqs_path)

            if pass_baseline_reqs_path.exists():
                pass_baseline_reqs_path.unlink()
            
            end_group()

            if not changed_packages_this_pass:
                print("\nNo effective version changes were possible in this pass. The system has converged.")
                break
        
        if final_successful_updates:
            self._print_final_summary(final_successful_updates, final_failed_updates)
            self._run_final_health_check()

    def _apply_pass_updates(self, successful_updates, baseline_reqs_path):
        print("\nApplying successful changes from this pass...")
        with open(baseline_reqs_path, "r") as f_read:
            lines = [line.strip() for line in f_read if line.strip()]

        for package, new_version in successful_updates.items():
             lines = [f"{package}=={new_version}" if self._get_package_name_from_spec(l) == package else l for l in lines]
        
        venv_dir = Path("./temp_venv")
        if venv_dir.exists(): shutil.rmtree(venv_dir)
        venv.create(venv_dir, with_pip=True)
        python_executable = str((venv_dir / "bin" / "python").resolve())

        temp_reqs_path = venv_dir / "final_pass_reqs.txt"
        with open(temp_reqs_path, "w") as f_write:
            f_write.write("\n".join(lines))
        
        _, stderr, returncode = run_command([python_executable, "-m", "pip", "install", "-r", str(temp_reqs_path)])
        if returncode != 0:
            print(f"CRITICAL: Failed to install combined updates at end of pass. Reverting. Error: {stderr}", file=sys.stderr)
            shutil.copy(baseline_reqs_path, self.requirements_path)
            return

        final_packages, _, _ = run_command([python_executable, "-m", "pip", "freeze"])
        with open(self.requirements_path, "w") as f:
            f.write(self._prune_pip_freeze(final_packages))
        print("Successfully applied and froze all successful updates for this pass.")

    def _calculate_update_risk(self, package, current_ver, target_ver):
        usage = self.usage_scores.get(package, 0)
        is_primary = 1 if package in self.primary_packages else 0
        try:
            old_v, new_v = parse_version(current_ver), parse_version(target_ver)
            if new_v.major > old_v.major: semver_severity = 3
            elif new_v.minor > old_v.minor: semver_severity = 2
            else: semver_severity = 1
        except: semver_severity = 1
        return (usage * 5.0) + (is_primary * 3.0) + (semver_severity * 2.0)

    def _print_final_summary(self, successful, failed):
        print("\n" + "#"*70); print("### OVERALL UPDATE RUN SUMMARY ###")
        if successful:
            print("\n[SUCCESS] The following packages were successfully updated:")
            print(f"{'Package':<30} | {'Target Version':<20} | {'Reached Version':<20}")
            print(f"{'-'*30} | {'-'*20} | {'-'*20}")
            for pkg, (target_ver, version) in successful.items(): print(f"{pkg:<30} | {target_ver:<20} | {version:<20}")
        if failed:
            print("\n[FAILURE] Updates were attempted but FAILED for:")
            print(f"{'Package':<30} | {'Target Version':<20} | {'Reason for Failure'}")
            print(f"{'-'*30} | {'-'*20} | {'-'*40}")
            for pkg, (target_ver, reason) in failed.items(): print(f"{pkg:<30} | {target_ver:<20} | {reason}")
        print("#"*70 + "\n")

    def _run_final_health_check(self):
        print("\n" + "#"*70); print("### SYSTEM HEALTH CHECK ###"); print("#"*70 + "\n")
        venv_dir = Path("./final_venv")
        if venv_dir.exists(): shutil.rmtree(venv_dir)
        venv.create(venv_dir, with_pip=True)
        python_executable = str((venv_dir / "bin" / "python").resolve())

        _, stderr, returncode = run_command([python_executable, "-m", "pip", "install", "-r", str(self.requirements_path)])
        if returncode != 0:
            print(f"CRITICAL ERROR: Final installation of combined dependencies failed! Error:\n{stderr}", file=sys.stderr)
            return

        success, metrics, _ = validate_changes(python_executable, self.config, group_title="Final System Health Check")
        if success and metrics and "not available" not in metrics:
            print("\n" + "="*70); print("=== METRICS FOR THE FULLY UPDATED ENVIRONMENT ===")
            print("\n".join([f"  {line}" for line in metrics.split('\n')])); print("="*70)
        elif success:
            print("\n" + "="*70); print("=== Final validation passed (no metrics). ==="); print("="*70)
        else:
            print("\n" + "!"*70); print("!!! CRITICAL ERROR: Final validation failed! !!!"); print("!"*70)

    def get_latest_version(self, package_name):
        try:
            page = self.pypi.get_project_page(package_name)
            if not (page and page.packages): return None
            stable_versions = [p.version for p in page.packages if p.version and not parse_version(p.version).is_prerelease]
            if stable_versions:
                return max(stable_versions, key=parse_version)
            all_versions = [p.version for p in page.packages if p.version]
            return max(all_versions, key=parse_version) if all_versions else None
        except Exception: return None

    def _try_install_and_validate(self, package_to_update, new_version, dynamic_constraints, baseline_reqs_path, is_probe, changed_packages):
        venv_dir = Path("./temp_venv")
        if venv_dir.exists(): shutil.rmtree(venv_dir)
        venv.create(venv_dir, with_pip=True)
        python_executable = str((venv_dir / "bin" / "python").resolve())
        
        temp_reqs_path = venv_dir / "temp_requirements.txt"
        with open(baseline_reqs_path, "r") as f_read, open(temp_reqs_path, "w") as f_write:
            lines = [f"{package_to_update}=={new_version}" if self._get_package_name_from_spec(l) == package_to_update else l.strip() for l in f_read if l.strip() and not l.strip().startswith('#')]
            f_write.write("\n".join(lines))

        _, stderr_install, returncode = run_command([python_executable, "-m", "pip", "install", "-r", str(temp_reqs_path)])
        
        if returncode != 0:
            print("INFO: Main installation failed. Retrying with verbose logging to identify conflicting packages...")
            _, stderr_for_logs, _ = run_command([python_executable, "-m", "pip", "install"] + temp_reqs_path.read_text().splitlines())
            
            conflict_match = re.search(r"Cannot install(?P<packages>[\s\S]+?)because", stderr_for_logs)
            reason = ""
            if conflict_match:
                conflicting_packages = ' '.join(conflict_match.group('packages').split()).replace(' and ', ', ').replace(',', ', ')
                reason = f"Conflict between packages: {conflicting_packages}"
                print(f"DIAGNOSIS: {reason}")
            else:
                llm_summary = self._ask_llm_to_summarize_error(stderr_install)
                reason = f"Installation conflict. Summary: {llm_summary}"
            
            return False, reason, stderr_install

        old_version = "N/A"
        with open(baseline_reqs_path, 'r') as f:
             for line in f:
                 if self._get_package_name_from_spec(line) == package_to_update:
                     if '==' in line: old_version = line.split('==')[1]

        if new_version == old_version and not changed_packages:
             return True, "Validation skipped (no change)", ""

        group_title = f"Validation for {package_to_update}=={new_version}"
        val_success, metrics, val_output = validate_changes(python_executable, self.config, group_title=group_title)

        if not val_success:
            return False, "Validation script failed", val_output
        return True, metrics, ""

    def attempt_update_with_healing(self, package, current_version, target_version, dynamic_constraints, baseline_reqs_path, changed_packages_this_pass):
        package_label = "(Primary)" if package in self.primary_packages else "(Transient)"
        
        success, result_data, stderr = self._try_install_and_validate(
            package, target_version, dynamic_constraints, baseline_reqs_path, 
            is_probe=False, changed_packages=changed_packages_this_pass
        )
        
        if success:
            return True, result_data if "skipped" in str(result_data) else target_version, None

        print(f"\nINFO: Initial update for '{package}' failed. Reason: '{result_data}'")
        start_group("View Full Error Log for Initial Failure"); print(stderr); end_group()
        print("INFO: Entering unified healing mode.")

        version_candidates = self._ask_llm_for_version_candidates(package, target_version)
        if version_candidates:
            for candidate in version_candidates:
                if parse_version(candidate) <= parse_version(current_version): continue
                print(f"INFO: Attempting LLM-suggested backtrack for {package} to {candidate}")
                success, result_data, _ = self._try_install_and_validate(
                    package, candidate, dynamic_constraints, baseline_reqs_path,
                    is_probe=False, changed_packages=changed_packages_this_pass
                )
                if success:
                    return True, candidate, None

        print(f"INFO: LLM suggestions failed. Falling back to Binary Search backtracking.")
        found_version = self._binary_search_backtrack(
            package, current_version, target_version, dynamic_constraints, 
            baseline_reqs_path, changed_packages_this_pass
        )
        if found_version:
            return True, found_version, None
        return False, "All backtracking attempts failed.", None
    
    def _binary_search_backtrack(self, package, last_good_version, failed_version, dynamic_constraints, baseline_reqs_path, changed_packages):
        start_group(f"Binary Search Backtrack for {package}")
        
        versions = self.get_all_versions_between(package, last_good_version, failed_version)
        if last_good_version not in versions:
            versions.insert(0, last_good_version)
        
        best_working_version = None
        for test_version in reversed(versions):
            print(f"Binary Search: Probing version {test_version}...")
            
            success, reason_or_metrics, _ = self._try_install_and_validate(
                package, test_version, dynamic_constraints, 
                baseline_reqs_path, is_probe=True, changed_packages=changed_packages
            )
            
            if success:
                if "skipped" in str(reason_or_metrics):
                    print(f"  --> {reason_or_metrics}")
                print(f"Binary Search: Version {test_version} PASSED probe.")
                best_working_version = test_version
                break 
            else:
                print(f"Binary Search: Version {test_version} FAILED probe. Reason: {reason_or_metrics}")
        
        end_group()
        if best_working_version:
            print(f"Binary Search SUCCESS: Found latest stable version: {best_working_version}")
            return best_working_version
            
        print(f"Binary Search FAILED: No stable version was found for {package}.")
        return None
    
    def get_all_versions_between(self, package_name, start_ver_str, end_ver_str):
        try:
            page = self.pypi.get_project_page(package_name)
            if not (page and page.packages): return []
            start_v, end_v = parse_version(start_ver_str), parse_version(end_ver_str)
            candidate_versions = {parse_version(p.version) for p in page.packages if p.version and start_v <= parse_version(p.version) < end_v and not getattr(parse_version(p.version), 'is_prerelease', False)}
            return sorted([str(v) for v in candidate_versions], key=parse_version)
        except Exception: return []

    def _prune_pip_freeze(self, freeze_output):
        lines = freeze_output.strip().split('\n')
        pruned_lines = [
            line for line in lines 
            if ('==' in line and not line.startswith('-e')) or line.startswith('-e')
        ]
        return "\n".join(pruned_lines)
    
    def _ask_llm_for_root_cause(self, package, error_message):
        if not self.llm_available: return {}
        py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        with open(self.config["REQUIREMENTS_FILE"], "r") as f:
            current_requirements = f.read()
        prompt = f"""You are an expert Python dependency diagnostician AI. Analyze the error that occurred when updating '{package}' in a project with these requirements:
---
{current_requirements}
---
The error on Python {py_version} was:
---
{error_message}
---
Respond in JSON. Is the root_cause 'self' or 'incompatibility'? If incompatibility, name the 'package' and 'suggested_constraint'. Example: {{"root_cause": "incompatibility", "package": "numpy", "suggested_constraint": "<2.0"}}"""
        try:
            response = self.llm.generate_content(prompt)
            json_text = re.search(r'\{.*\}', response.text, re.DOTALL).group(0)
            return json.loads(json_text)
        except Exception: return {}

    def _ask_llm_for_version_candidates(self, package, failed_version):
        if not self.llm_available: return []
        prompt = f"Give a Python list of the {self.config['MAX_LLM_BACKTRACK_ATTEMPTS']} most recent, previous release versions of the python package '{package}', starting from the version just before '{failed_version}'. The list must be in descending order. Respond ONLY with the list."
        try:
            response = self.llm.generate_content(prompt)
            match = re.search(r'(\[.*?\])', response.text, re.DOTALL)
            if not match: return []
            return ast.literal_eval(match.group(1))
        except ResourceExhausted:
            self.llm_available = False; return []
        except Exception: return []

    def _ask_llm_to_summarize_error(self, error_message):
        if not self.llm_available: return "(LLM unavailable due to quota)"
        prompt = f"The following is a Python pip install error log. Please summarize the root cause of the conflict in a single, concise sentence. Error Log: --- {error_message} ---"
        try:
            response = self.llm.generate_content(prompt)
            return response.text.strip().replace('\n', ' ')
        except Exception: return "Failed to get summary from LLM."