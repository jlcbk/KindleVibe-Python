#!/usr/bin/env python3
"""
把 vibe coding 状态写入 KindleVibe-Python 的小工具。
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, request


DEFAULT_URL = "http://localhost:8080/api/vibe"
PRESET_NAMES = ("coding", "review", "blocked", "done")
PRESET_DIR = Path(__file__).resolve().parent / "examples" / "payloads"


def default_url() -> str:
    return os.environ.get("KINDLEVIBE_URL", DEFAULT_URL)


def default_token() -> str:
    return os.environ.get("KINDLEVIBE_TOKEN", "")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="读取或更新 KindleVibe 的 vibe coding 状态"
    )
    parser.add_argument(
        "--url",
        default=default_url(),
        help="KindleVibe API 地址；默认读取 KINDLEVIBE_URL，未设置时使用本机 8080"
    )
    parser.add_argument(
        "--token",
        default=default_token(),
        help="可选 API 写入 token；默认读取 KINDLEVIBE_TOKEN"
    )
    parser.add_argument("--state", help="当前状态，例如：编码中、等待评审、被阻塞")
    parser.add_argument("--project", help="当前项目")
    parser.add_argument("--branch", help="当前分支或工作区")
    parser.add_argument("--objective", help="当前大目标")
    parser.add_argument("--current-task", dest="current_task", help="当前任务")
    parser.add_argument("--next-action", dest="next_action", help="下一步行动")
    parser.add_argument(
        "--participant",
        action="append",
        default=None,
        help="参与者，可重复传入"
    )
    parser.add_argument(
        "--blocker",
        action="append",
        default=None,
        help="阻塞项，可重复传入；不传表示不修改"
    )
    parser.add_argument(
        "--clear-blockers",
        action="store_true",
        help="清空阻塞项；不能和 --blocker 同时使用"
    )
    parser.add_argument(
        "--clear-participants",
        action="store_true",
        help="清空参与者；不能和 --participant 同时使用"
    )
    parser.add_argument("--event", help="追加一条最近事件")
    parser.add_argument(
        "--clear-events",
        action="store_true",
        help="清空最近事件；可以和 --event 一起使用以保留一条新事件"
    )
    parser.add_argument(
        "--heartbeat",
        action="store_true",
        help="只刷新更新时间，用来表示当前状态仍然有效"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出完整 JSON，而不是中文摘要"
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="读取 /api/health 并输出服务健康状态"
    )
    parser.add_argument(
        "--payload-file",
        help="从 JSON 文件读取状态包，命令行参数会覆盖文件中的同名字段"
    )
    parser.add_argument(
        "--preset",
        choices=PRESET_NAMES,
        help="读取内置状态包：coding、review、blocked、done"
    )
    parser.add_argument("--timeout", type=float, default=5.0, help="请求超时时间")
    parser.add_argument(
        "--from-git",
        action="store_true",
        help="从当前 Git 仓库自动填充项目名和分支"
    )
    parser.add_argument("--cwd", default=".", help="配合 --from-git 使用的工作目录")
    return parser.parse_args(argv)


def clean_text(value: Optional[str]) -> str:
    return value.strip() if value else ""


def clean_list(values) -> list:
    if values is None:
        return []
    return [item for item in (clean_text(value) for value in values) if item]


def git_output(cwd: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def detect_git_context(cwd: str) -> Dict[str, str]:
    root = git_output(cwd, "rev-parse", "--show-toplevel")
    if not root:
        return {}

    branch = git_output(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        short_sha = git_output(cwd, "rev-parse", "--short", "HEAD")
        branch = f"detached:{short_sha}" if short_sha else "detached"

    context = {"project": Path(root).name}
    if branch:
        context["branch"] = branch
    return context


def load_payload_file(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except OSError as e:
        raise ValueError(f"无法读取状态文件：{e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"状态文件不是有效 JSON：{e}") from e

    if not isinstance(payload, dict):
        raise ValueError("状态文件顶层必须是 JSON 对象")
    return payload


def load_preset_payload(name: Optional[str]) -> Dict[str, Any]:
    if not name:
        return {}
    return load_payload_file(str(PRESET_DIR / f"{name}.json"))


def build_payload(args) -> Dict[str, Any]:
    if args.preset and args.payload_file:
        raise ValueError("不能同时使用 --preset 和 --payload-file")
    if args.clear_blockers and args.blocker is not None:
        raise ValueError("不能同时使用 --blocker 和 --clear-blockers")
    if args.clear_participants and args.participant is not None:
        raise ValueError("不能同时使用 --participant 和 --clear-participants")

    if args.preset:
        payload: Dict[str, Any] = load_preset_payload(args.preset)
    else:
        payload = load_payload_file(args.payload_file)
    for field in (
        "state",
        "project",
        "branch",
        "objective",
        "current_task",
        "next_action",
        "event",
    ):
        value = clean_text(getattr(args, field, ""))
        if value:
            payload[field] = value

    if args.participant is not None:
        payload["participants"] = clean_list(args.participant)
    elif args.clear_participants:
        payload["participants"] = []

    if args.blocker is not None:
        payload["blockers"] = clean_list(args.blocker)
    elif args.clear_blockers:
        payload["blockers"] = []

    if args.clear_events:
        payload["events"] = []

    if args.heartbeat:
        payload["heartbeat"] = True
    if args.from_git:
        for key, value in detect_git_context(args.cwd).items():
            payload.setdefault(key, value)

    return payload


def request_vibe(
    url: str,
    payload: Optional[Dict[str, Any]],
    timeout: float,
    token: str = "",
) -> Dict[str, Any]:
    data = None
    headers = {}
    method = "GET"
    if payload:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
        method = "POST"
    if token:
        headers["X-KindleVibe-Token"] = token

    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"服务返回 {e.code}：{body}") from e
    except error.URLError as e:
        raise RuntimeError(f"无法连接 KindleVibe：{e}") from e


def derive_health_url(url: str) -> str:
    url = url.rstrip("/")
    if url.endswith("/api/vibe"):
        return url[:-len("/api/vibe")] + "/api/health"
    if url.endswith("/api/health"):
        return url
    return url + "/api/health"


def format_summary(status: Dict[str, Any]) -> str:
    blockers = status.get("blockers") or []
    participants = status.get("participants") or []
    events = status.get("events") or []
    last_event = events[-1].get("text", "") if events and isinstance(events[-1], dict) else "暂无"

    lines = [
        f"状态：{status.get('state', '未知')}",
        f"项目：{status.get('project', '未指定')} / 分支：{status.get('branch', '未指定')}",
        f"目标：{status.get('objective', '未指定')}",
        f"当前任务：{status.get('current_task', '未指定')}",
        f"下一步：{status.get('next_action', '未指定')}",
        f"参与者：{', '.join(participants) if participants else '未指定'}",
        f"阻塞项：{', '.join(blockers) if blockers else '无'}",
        f"最近事件：{last_event}",
        f"更新时间：{status.get('updated_at', '未知')}",
    ]
    return "\n".join(lines)


def format_health_summary(health: Dict[str, Any]) -> str:
    vibe = health.get("vibe") or {}
    codex = health.get("codex") or {}
    codex_error = codex.get("error") or "无"
    stale = "可能过期" if vibe.get("stale") else "正常"

    lines = [
        f"服务：{health.get('status', '未知')}",
        f"检查时间：{health.get('checked_at', '未知')}",
        f"Vibe 状态：{vibe.get('state', '未知')}",
        f"Vibe 心跳：{stale}",
        f"Vibe 更新时间：{vibe.get('updated_at', '未知')}",
        f"Codex 数据来源：{codex.get('source', '未知')}",
        f"Codex 错误：{codex_error}",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.health:
        try:
            health = request_vibe(derive_health_url(args.url), None, args.timeout, args.token)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps(health, indent=2, ensure_ascii=False))
        else:
            print(format_health_summary(health))
        return 0

    try:
        payload = build_payload(args)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        status = request_vibe(args.url, payload if payload else None, args.timeout, args.token)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(format_summary(status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
