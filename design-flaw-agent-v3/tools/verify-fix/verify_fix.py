#!/usr/bin/env python3
"""
verify_fix.py — Fix verification harness (item #5)
=====================================================
A "powerful" agent shouldn't just suggest a fix — it should prove the fix
compiles/lints before presenting it as correct. This script:

  1. Takes a unified diff (the proposed fix) and a target repo.
  2. Applies it to a TEMPORARY COPY of the repo (never touches the original).
  3. Runs the appropriate build/lint command based on detected stack:
       - .NET:    dotnet build
       - Java:    mvn -q compile   (or gradle compileJava if gradlew present)
       - Angular: npx tsc --noEmit  (fast type-check, avoids full ng build)
  4. Reports PASS/FAIL with captured output.
  5. Cleans up the temp copy afterward.

This gives the Copilot agent a way to say "here is a fix, and I verified it
compiles" instead of "here is a fix that looks right."

Usage:
    python3 verify_fix.py <repo_root> --diff fix.patch --stack dotnet
    python3 verify_fix.py <repo_root> --diff fix.patch --stack java
    python3 verify_fix.py <repo_root> --diff fix.patch --stack angular
    python3 verify_fix.py <repo_root> --diff fix.patch --stack auto   (detect)

The diff file should be a standard unified diff (as produced by `git diff`
or by the agent itself), with paths relative to repo_root.

Exit codes: 0 = fix applied and build/lint passed
            1 = diff failed to apply
            2 = build/lint failed
            3 = no recognized project / command not available
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def detect_stack(repo_root):
    has_dotnet = any(f.endswith((".csproj", ".sln")) for _, _, files in os.walk(repo_root) for f in files)
    has_java = any(f in ("pom.xml", "build.gradle", "build.gradle.kts")
                    for _, _, files in os.walk(repo_root) for f in files)
    has_ng = os.path.exists(os.path.join(repo_root, "angular.json")) or \
             os.path.exists(os.path.join(repo_root, "package.json"))

    detected = []
    if has_dotnet:
        detected.append("dotnet")
    if has_java:
        detected.append("java")
    if has_ng:
        detected.append("angular")
    return detected


def which(cmd):
    return shutil.which(cmd) is not None


def run(cmd, cwd, timeout=300):
    try:
        result = subprocess.run(
            cmd, cwd=cwd, shell=isinstance(cmd, str),
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return -1, "", str(e)


def apply_diff(temp_root, diff_path):
    rc, out, err = run(["git", "apply", "--whitespace=nowarn", os.path.abspath(diff_path)], cwd=temp_root)
    if rc != 0:
        # try patch as fallback
        rc2, out2, err2 = run(["patch", "-p1", "-i", os.path.abspath(diff_path)], cwd=temp_root)
        if rc2 != 0:
            return False, f"git apply failed:\n{err}\n\npatch fallback failed:\n{err2}"
    return True, ""


def build_dotnet(temp_root):
    if not which("dotnet"):
        return 3, "dotnet CLI not available in this environment"
    rc, out, err = run(["dotnet", "build", "--nologo", "-v", "quiet"], cwd=temp_root, timeout=600)
    return rc, (out + "\n" + err)


def build_java(temp_root):
    if os.path.exists(os.path.join(temp_root, "mvnw")):
        cmd = ["./mvnw", "-q", "compile"]
    elif which("mvn"):
        cmd = ["mvn", "-q", "compile"]
    elif os.path.exists(os.path.join(temp_root, "gradlew")):
        cmd = ["./gradlew", "compileJava", "-q"]
    elif which("gradle"):
        cmd = ["gradle", "compileJava", "-q"]
    else:
        return 3, "No Maven/Gradle wrapper or CLI available"
    rc, out, err = run(cmd, cwd=temp_root, timeout=600)
    return rc, (out + "\n" + err)


def build_angular(temp_root):
    if not which("npx"):
        return 3, "npx not available"
    if not os.path.exists(os.path.join(temp_root, "node_modules")):
        return 3, "node_modules not installed in repo — run `npm ci` first (skipped here to save time)"
    rc, out, err = run(["npx", "tsc", "--noEmit"], cwd=temp_root, timeout=300)
    return rc, (out + "\n" + err)


BUILDERS = {
    "dotnet": build_dotnet,
    "java": build_java,
    "angular": build_angular,
}


def main():
    parser = argparse.ArgumentParser(description="Apply a proposed fix to a temp copy and verify it builds/lints")
    parser.add_argument("repo_root")
    parser.add_argument("--diff", required=True, help="Path to unified diff file with the proposed fix")
    parser.add_argument("--stack", choices=["dotnet", "java", "angular", "auto"], default="auto")
    parser.add_argument("--keep-temp", action="store_true", help="Don't delete the temp copy (for debugging)")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    if not os.path.isdir(repo_root):
        print(f"Error: {repo_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    if args.stack == "auto":
        stacks = detect_stack(repo_root)
        if not stacks:
            print("Could not detect a recognized stack (.NET/Java/Angular). Specify --stack explicitly.")
            sys.exit(3)
        if len(stacks) > 1:
            print(f"Multiple stacks detected ({stacks}); using the first. Specify --stack to override.")
        stack = stacks[0]
    else:
        stack = args.stack

    print(f"Stack: {stack}")
    print(f"Copying repo to temp directory for sandboxed verification...")

    temp_dir = tempfile.mkdtemp(prefix="verify_fix_")
    temp_root = os.path.join(temp_dir, "repo")
    try:
        shutil.copytree(
            repo_root, temp_root,
            ignore=shutil.ignore_patterns(
                "node_modules", "bin", "obj", "dist", "build", ".git",
                "target", ".angular", "coverage", "__pycache__",
            ),
        )

        print("Applying diff...")
        ok, err = apply_diff(temp_root, args.diff)
        if not ok:
            print("FAIL: diff did not apply")
            print(err)
            sys.exit(1)

        print(f"Running build/lint for {stack}...")
        rc, output = BUILDERS[stack](temp_root)

        if rc == 3:
            print("SKIPPED: " + output)
            sys.exit(3)
        elif rc == 0:
            print("PASS: fix applies and builds/lints cleanly")
            sys.exit(0)
        else:
            print("FAIL: build/lint failed after applying fix")
            print(output[-4000:])  # last 4000 chars to avoid huge dumps
            sys.exit(2)

    finally:
        if not args.keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            print(f"Temp copy kept at: {temp_root}")


if __name__ == "__main__":
    main()
