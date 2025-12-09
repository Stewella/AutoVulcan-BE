import os
import subprocess
import json
import re
from typing import List, Dict, Optional

from config import settings

EXCLUDE_DIRS = {"target", "build", ".git", ".idea", ".gradle"}


def _collect_java_files(root: str) -> List[str]:
    java_files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            if f.endswith(".java"):
                java_files.append(os.path.join(dirpath, f))
    return java_files


def _list_compiled_classes(classes_root: str) -> List[str]:
    classes: List[str] = []
    if not os.path.isdir(classes_root):
        return classes
    for dirpath, dirnames, filenames in os.walk(classes_root):
        for f in filenames:
            if f.endswith(".class") and not f.endswith("$1.class"):
                rel = os.path.relpath(os.path.join(dirpath, f), classes_root)
                fqcn = rel.replace(".class", "").replace(os.sep, ".")
                classes.append(fqcn)
    return classes


def _docker_run(image: str, mounts: List[str], bash_cmd: str, timeout: int) -> subprocess.CompletedProcess:
    cmd = [
        "docker", "run", "--rm",
    ]
    for m in mounts:
        cmd.extend(["-v", m])
    cmd.extend([image, "bash", "-lc", bash_cmd])
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def _find_classes_with_method(root: str, method_name: str) -> List[str]:
    """Scan Java sources to find classes that declare or reference the given method name.
    Returns a list of simple class names (file names without .java).
    """
    matches: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            if f.endswith(".java"):
                p = os.path.join(dirpath, f)
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                        txt = fh.read()
                    if re.search(rf"\b{re.escape(method_name)}\s*\(", txt):
                        matches.add(f[:-5])
                except Exception:
                    pass
    return list(matches)


def _extract_reachability_from_tests(source_dir: str, tests_root: str, method_name: str) -> List[Dict]:
    """Parse EvoSuite-generated test files to find calls to the target method and basic test method names."""
    result: List[Dict] = []
    for dirpath, _, filenames in os.walk(tests_root):
        for f in filenames:
            if f.endswith(".java"):
                p = os.path.join(dirpath, f)
                occurrences = []
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                        for idx, line in enumerate(fh, start=1):
                            if re.search(rf"\b{re.escape(method_name)}\s*\(", line):
                                occurrences.append({"line": idx, "code": line.strip()})
                except Exception:
                    continue
                if occurrences:
                    # attempt to find test method identifiers
                    try:
                        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                            text = fh.read()
                        test_methods = re.findall(r"void\s+(test[\w_]*)\s*\(", text)
                    except Exception:
                        test_methods = []
                    result.append({
                        "test_file": os.path.relpath(p, source_dir),
                        "occurrences": occurrences,
                        "test_methods": test_methods,
                    })
    return result


def run_evosuite_in_docker(source_dir: str, timeout: int = 600, max_classes: int = 10, search_budget: Optional[int] = None, target_method_name: Optional[str] = None) -> Dict:
    """
    Compile and run EvoSuite directly inside the backend container.

    Behavior:
    - If a Maven project is detected (pom.xml present), use Maven to compile sources and resolve dependencies,
      and build a classpath file. EvoSuite will run with the full project classpath.
    - If no Maven project is detected, fall back to plain javac compilation of all .java files.

    Returns a payload dict with EvoSuite generation metadata and call traces.
    """
    if not settings.EVOSUITE_ENABLED:
        return {"status": "skipped", "reason": "EvoSuite disabled via settings.EVOSUITE_ENABLED"}
    jar_path = settings.EVOSUITE_JAR_PATH or "/opt/tools/evosuite.jar"
    if search_budget is None:
        search_budget = settings.EVOSUITE_SEARCH_BUDGET

    if not jar_path or not os.path.exists(jar_path):
        raise RuntimeError("EvoSuite jar is not configured or not found. Set EVOSUITE_JAR_PATH in .env to a valid path or mount /opt/tools/evosuite.jar.")

    if not os.path.isdir(source_dir):
        raise RuntimeError(f"Source directory not found: {source_dir}")

    java_files = _collect_java_files(source_dir)
    if not java_files:
        raise RuntimeError("No Java source files found in the provided directory.")

    classes_root = os.path.join(source_dir, "target", "classes")
    tests_root = os.path.join(source_dir, "evosuite-tests")
    os.makedirs(classes_root, exist_ok=True)
    os.makedirs(tests_root, exist_ok=True)

    pom_path = os.path.join(source_dir, "pom.xml")
    payload: Dict = {
        "runtime": "in_container",
        "jar_path": jar_path,
        "search_budget": search_budget,
        "compile": {},
        "generated_tests": [],
        "target_method": target_method_name,
    }

    if os.path.isfile(pom_path):
        # Maven-based compilation and classpath resolution
        compile_cmd = "mvn -q -DskipTests clean compile"
        compile_proc = subprocess.run(["bash", "-lc", compile_cmd], cwd=source_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)

        payload["compile"] = {
            "stdout": compile_proc.stdout,
            "stderr": compile_proc.stderr,
            "status": "success" if compile_proc.returncode == 0 else "failed",
        }

        if compile_proc.returncode != 0:
            payload["error"] = "Maven compilation failed"
            return payload

        # Build classpath file
        cp_cmd = "mvn -q dependency:build-classpath -Dmdep.outputFile=target/classpath.txt"
        cp_proc = subprocess.run(["bash", "-lc", cp_cmd], cwd=source_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)

        deps_cp = ""
        classpath_file = os.path.join(source_dir, "target", "classpath.txt")
        if os.path.exists(classpath_file):
            try:
                with open(classpath_file, "r") as f:
                    deps_cp = f.read().strip()
            except Exception:
                deps_cp = ""
        # Project classpath: compiled classes + dependencies
        project_cp = classes_root if not deps_cp else f"{classes_root}:{deps_cp}"
    else:
        # Fallback: plain javac compilation (no external dependencies)
        compile_cmd = (
            "mkdir -p target/classes && "
            "find . -type f -name '*.java' -not -path '*/target/*' -not -path '*/build/*' -print0 | "
            "xargs -0 javac -d target/classes"
        )
        compile_proc = subprocess.run(["bash", "-lc", compile_cmd], cwd=source_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        payload["compile"] = {
            "stdout": compile_proc.stdout,
            "stderr": compile_proc.stderr,
            "status": "success" if compile_proc.returncode == 0 else "failed",
        }
        if compile_proc.returncode != 0:
            payload["error"] = "Compilation failed"
            return payload
        project_cp = classes_root

    # List compiled classes and run EvoSuite for up to max_classes
    compiled_classes = _list_compiled_classes(classes_root)
    payload["compiled_classes_count"] = len(compiled_classes)

    if not compiled_classes:
        payload["error"] = "No compiled classes found after compilation"
        return payload

    if target_method_name:
        simple_matches = _find_classes_with_method(source_dir, target_method_name)
        filtered = [c for c in compiled_classes if c.split(".")[-1] in simple_matches]
        classes_to_test = filtered[:max_classes] if filtered else compiled_classes[:max_classes]
    else:
        classes_to_test = compiled_classes[:max_classes]

    for cls in classes_to_test:
        evosuite_cmd = (
            f"java -jar {jar_path} "
            f"-class {cls} "
            f"-projectCP {project_cp} "
            f"-Dsearch_budget={search_budget} "
            f"-Djunit_suffix=Test "
            f"-Doutput_directory={tests_root} "
            f"-Dreport_dir={tests_root}/reports"
        )
        proc = subprocess.run(["bash", "-lc", evosuite_cmd], cwd=source_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)

        simple = cls.split(".")[-1]
        generated: List[str] = []
        for dirpath, _, filenames in os.walk(tests_root):
            for f in filenames:
                if f.endswith(".java") and simple in f and "Test" in f:
                    generated.append(os.path.relpath(os.path.join(dirpath, f), source_dir))

        payload["generated_tests"].append({
            "class": cls,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "status": "success" if proc.returncode == 0 else "failed",
            "test_files": generated,
        })

    if target_method_name:
        payload["reachability"] = _extract_reachability_from_tests(source_dir, tests_root, target_method_name)

    return payload
