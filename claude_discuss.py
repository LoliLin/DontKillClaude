#!/usr/bin/env python3
"""Run configured prompt sequences with the Claude Code CLI."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(text: str) -> str:
    """Remove common credential-shaped strings before errors are persisted."""
    text = re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)\S+", r"\1[REDACTED]", text)
    return text


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config.get("sequences"), list) or not config["sequences"]:
        raise ValueError("配置必须包含至少一个 sequences 项")
    if config.get("conversation_mode", "independent") not in ("independent", "chained"):
        raise ValueError("conversation_mode 必须是 independent 或 chained")
    for sequence in config["sequences"]:
        if not isinstance(sequence.get("messages"), list) or not sequence["messages"]:
            raise ValueError("每个 sequence 都必须包含非空 messages")
    return config


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def run_prompt(command: str, prompt: str, timeout: int, session_id: str | None, create_session: bool = False) -> tuple[int, str, str]:
    args = [command, "-p", prompt, "--output-format", "text"]
    if create_session and session_id:
        args.extend(["--session-id", session_id])
    elif session_id:
        args.extend(["--resume", session_id])
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return 124, stdout, f"Timed out after {timeout} seconds. {stderr}"


def run_round(config: dict[str, Any], transcript: Path, round_number: int) -> bool:
    command = str(config.get("claude_command", "claude"))
    if not shutil.which(command):
        print(f"找不到 Claude CLI：{command}", file=sys.stderr)
        return False

    mode = config.get("conversation_mode", "independent")
    for sequence in config["sequences"]:
        session_id = str(uuid.uuid4()) if mode == "chained" else None
        for index, prompt in enumerate(sequence["messages"], start=1):
            call_session = session_id
            code, stdout, stderr = run_prompt(
                command, str(prompt), int(config.get("timeout_seconds", 300)), call_session,
                create_session=(mode == "chained" and index == 1),
            )
            record = {
                "timestamp": utc_now(),
                "round": round_number,
                "sequence": sequence.get("name", "unnamed"),
                "turn": index,
                "conversation_mode": mode,
                "session_id": session_id if mode == "chained" else None,
                "prompt": str(prompt),
                "return_code": code,
                "response": stdout,
                "error": redact(stderr)[-4000:] if stderr else None,
            }
            append_record(transcript, record)
            if code:
                print(
                    f"[{sequence.get('name', 'unnamed')}:{index}] CLI 失败（退出码 {code}）；详情已写入 transcript。",
                    file=sys.stderr,
                )
                return False
            print(f"[{sequence.get('name', 'unnamed')}:{index}] 完成")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="按配置重复运行 Claude CLI 对话序列")
    parser.add_argument("--config", default="config.json", help="JSON 配置路径")
    parser.add_argument("--once", action="store_true", help="只运行一轮，忽略配置中的 rounds")
    args = parser.parse_args()
    try:
        config = load_config(Path(args.config))
        rounds = 1 if args.once else config.get("rounds", 1)
        rounds = None if rounds in (None, 0, "forever") else int(rounds)
        interval = max(0, int(config.get("interval_seconds", 3600)))
        transcript = Path(config.get("transcript_path", "transcripts/discussions.jsonl"))
        if rounds is not None and rounds < 1:
            raise ValueError("rounds 必须大于 0、为 0/forever（无限轮）或不设置")
        round_number = 0
        while rounds is None or round_number < rounds:
            round_number += 1
            if not run_round(config, transcript, round_number):
                return 1
            if rounds is None or round_number < rounds:
                time.sleep(interval)
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"配置或运行错误：{redact(str(exc))}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已停止。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
