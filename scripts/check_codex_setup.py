"""Read-only installed-CLI compatibility check; starts no model turn and changes no settings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from typing import Any


def check(binary: Path, project: Path, trust_for_inspection: bool = False) -> dict[str, Any]:
    global_config = Path.home() / ".codex/config.toml"
    before = hashlib.sha256(global_config.read_bytes()).hexdigest() if global_config.exists() else None
    version = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    command = [str(binary), "app-server", "--strict-config"]
    if trust_for_inspection:
        # Process-only project discovery; never grants command-hook trust or writes settings.
        key = json.dumps(os.path.normcase(str(project.resolve())))
        command += ["-c", f'projects={{{key}={{trust_level="trusted"}}}}']
    messages: queue.Queue[dict[str, Any]] = queue.Queue()
    with subprocess.Popen(
        command,
        cwd=project,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    ) as process:
        assert process.stdin and process.stdout

        def reader() -> None:
            assert process.stdout
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except json.JSONDecodeError:
                    continue

        threading.Thread(target=reader, daemon=True).start()
        number = 0

        def request(method: str, params: dict[str, Any]) -> Any:
            nonlocal number
            number += 1
            assert process.stdin
            process.stdin.write(json.dumps({"id": number, "method": method, "params": params}) + "\n")
            process.stdin.flush()
            while True:
                result = messages.get(timeout=20)
                if result.get("id") == number:
                    if "error" in result:
                        raise RuntimeError(f"Compatibility request failed: {method}")
                    return result["result"]

        try:
            request(
                "initialize",
                {
                    "clientInfo": {"name": "newsresearch-setup-check", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            process.stdin.write('{"method":"initialized"}\n')
            process.stdin.flush()
            config = request("config/read", {"cwd": str(project), "includeLayers": True})
            hooks = request("hooks/list", {"cwds": [str(project)]})
            skills = request("skills/list", {"cwds": [str(project)], "forceReload": True})
            # Never write or print the complete effective/global configuration.
            effective = config.get("config", {})
            discovered_hooks = [
                {
                    key: hook.get(key)
                    for key in ["eventName", "handlerType", "command", "enabled", "trustStatus", "timeoutSec"]
                }
                for entry in hooks.get("data", [])
                for hook in entry["hooks"]
                if hook.get("source") == "project"
            ]
            discovered_skills = [
                {"name": skill["name"], "scope": skill.get("scope")}
                for entry in skills.get("data", [])
                for skill in entry["skills"]
                if skill["name"] in {"research-operations", "research-review", "research-measurement"}
            ]
            report = {
                "codex": version,
                "strict_config": True,
                "model_turns": 0,
                "process_only_project_trust_for_inspection": trust_for_inspection,
                "effective_project_doc_max_bytes": effective.get("project_doc_max_bytes"),
                "effective_hooks_feature": effective.get("features", {}).get("hooks"),
                "project_hooks": discovered_hooks,
                "project_skills": discovered_skills,
                "project_layers": [
                    {
                        "source": layer["name"],
                        "disabled_reason": layer.get("disabledReason"),
                        "declared_keys": sorted(layer.get("config", {})),
                    }
                    for layer in config.get("layers", [])
                    if layer["name"].get("type") == "project"
                ],
                "hook_error_count": sum(len(entry["errors"]) for entry in hooks.get("data", [])),
                "skill_error_count": sum(len(entry["errors"]) for entry in skills.get("data", [])),
            }
        finally:
            process.terminate()
            process.wait(timeout=10)
    after = hashlib.sha256(global_config.read_bytes()).hexdigest() if global_config.exists() else None
    report["global_config_unchanged"] = before == after
    if not report["global_config_unchanged"]:
        raise RuntimeError("Global configuration changed during read-only verification")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True, help="Installed codex executable")
    parser.add_argument(
        "--inspect-trusted-project",
        action="store_true",
        help="Process-only project discovery; never trusts hooks",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            check(args.binary, Path(__file__).resolve().parents[1], args.inspect_trusted_project), indent=2
        )
    )


if __name__ == "__main__":
    main()
