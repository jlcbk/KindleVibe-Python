#!/usr/bin/env python3
"""
InkDash: Dashboard for Codex usage and collaboration status on e-ink devices.
"""

import argparse
import copy
import re
import subprocess
import json
import logging
import sys
from http.cookies import CookieError, SimpleCookie
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse
import threading
import time
from typing import Optional, Dict, Any

from status_model import (
    MAX_EVENT_ITEMS,
    clean_text as _as_clean_text,
    default_status as default_vibe_status,
    event_list as _as_event_list,
    is_status_stale,
    merge_status_patch,
    normalize_status as normalize_vibe_status,
    now_display,
    parse_display_time,
    text_list as _as_text_list,
)


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging():
    """Configure logging with both file and console handlers."""
    logger = logging.getLogger("InkDash")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    
    # File handler
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "inkdash.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_format)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


logger = setup_logging()


# ============================================================================
# Configuration
# ============================================================================

CONFIG_FILE = Path(__file__).parent / "config.json"
STATUS_FILE = Path(__file__).parent / "inkdash_status.json"
STATUS_FILE_LEGACY = Path(__file__).parent / "vibe_status.json"
PRESET_DIR = Path(__file__).parent / "examples" / "payloads"
PRESET_NAMES = ("coding", "review", "blocked", "done")
LAYOUT_MODES = ("auto", "portrait", "landscape")
LAYOUT_MODE_LABELS = {
    "auto": "自动",
    "portrait": "竖屏",
    "landscape": "横屏",
}
TEXT_SCALE_MIN = 80
TEXT_SCALE_MAX = 200
TEXT_SCALE_DEFAULT = 125
TEXT_SCALE_QUICK_VALUES = (100, 125, 150, 200)
PREFERENCE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
LAYOUT_COOKIE = "inkdash_layout"
TEXT_SCALE_COOKIE = "inkdash_text_scale"

DEFAULT_CONFIG = {
    "server": {
        "port": 8080,
        "host": "0.0.0.0"
    },
    "refresh": {
        "interval_seconds": 300,
        "auto_refresh_page_ms": 300000
    },
    "codex": {
        "enabled": True,
        "source": "auto",
        "session_file_limit": 10
    },
    "status": {
        "stale_after_seconds": 900
    },
    "security": {
        "api_token": ""
    },
    "display": {
        "show_credits": False,
        "show_plan_type": True,
        "show_data_source": False,
        "show_last_updated": True,
        "show_status_board": False,
        "layout_mode": "auto",
        "text_scale_percent": TEXT_SCALE_DEFAULT
    }
}


def load_config() -> Dict[str, Any]:
    """Load configuration from file, creating default if not exists."""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
            logger.info(f"Configuration loaded from {CONFIG_FILE}")
            # Merge with defaults to ensure all keys exist
            return migrate_config(merge_configs(DEFAULT_CONFIG, loaded_config), loaded_config)
        else:
            logger.info("Config file not found, creating default configuration")
            default_config = copy.deepcopy(DEFAULT_CONFIG)
            save_config(default_config)
            return default_config
    except Exception as e:
        logger.error(f"Failed to load config: {e}, using defaults")
        return copy.deepcopy(DEFAULT_CONFIG)


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to file."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"Configuration saved to {CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def merge_configs(default: Dict, override: Dict) -> Dict:
    """Deep merge override into default config."""
    result = copy.deepcopy(default)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def migrate_config(config: Dict[str, Any], loaded_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply compatibility migrations for renamed config keys."""
    loaded_config = loaded_config or {}
    if "status" not in loaded_config and isinstance(loaded_config.get("vibe"), dict):
        legacy_stale_after = loaded_config["vibe"].get("stale_after_seconds")
        if legacy_stale_after is not None:
            config.setdefault("status", {})["stale_after_seconds"] = legacy_stale_after
    return config


def normalize_layout_mode(value: Any) -> str:
    """Return a supported dashboard layout mode."""
    mode = str(value or "").strip().lower()
    return mode if mode in LAYOUT_MODES else "auto"


def current_layout_mode() -> str:
    """Return the configured dashboard layout mode."""
    return normalize_layout_mode(config.get("display", {}).get("layout_mode", "auto"))


def normalize_text_scale(value: Any) -> int:
    """Return a supported dashboard text scale percentage."""
    try:
        scale = int(value)
    except (TypeError, ValueError):
        scale = TEXT_SCALE_DEFAULT
    return max(TEXT_SCALE_MIN, min(TEXT_SCALE_MAX, scale))


def clamp_int_range(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Return an integer clamped to a safe inclusive range."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def refresh_interval_seconds(value: Any = None) -> int:
    """Return a safe background refresh interval in seconds."""
    if value is None:
        value = config.get("refresh", {}).get("interval_seconds", 300)
    return clamp_int_range(value, 300, 30, 3600)


def page_refresh_seconds(value: Any = None) -> int:
    """Return a safe browser refresh interval in seconds."""
    if value is None:
        value = config.get("refresh", {}).get("auto_refresh_page_ms", 300000)
    try:
        seconds = int(value) // 1000
    except (TypeError, ValueError):
        seconds = 300
    return clamp_int_range(seconds, 300, 30, 3600)


def server_port_number(value: Any = None) -> int:
    """Return a safe server port number."""
    if value is None:
        value = config.get("server", {}).get("port", 8080)
    return clamp_int_range(value, 8080, 1, 65535)


def server_host_value(value: Any = None) -> str:
    """Return a non-empty server host string."""
    if value is None:
        value = config.get("server", {}).get("host", "0.0.0.0")
    host = str(value or "").strip()
    return host if host else "0.0.0.0"


def current_text_scale() -> int:
    """Return the configured dashboard text scale percentage."""
    return normalize_text_scale(
        config.get("display", {}).get("text_scale_percent", TEXT_SCALE_DEFAULT)
    )


def config_bool(value: Any, default: bool = False) -> bool:
    """Return a boolean for config values that may be hand-edited as strings."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "y"}:
            return True
        if normalized in {"0", "false", "no", "off", "n", ""}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def display_flag(display: Dict[str, Any], key: str) -> bool:
    """Return a display flag using DEFAULT_CONFIG as the fallback source."""
    return config_bool(
        display.get(key),
        bool(DEFAULT_CONFIG.get("display", {}).get(key, False)),
    )


def codex_enabled_flag(value: Any = None) -> bool:
    """Return whether Codex usage fetching is enabled."""
    if value is None:
        value = config.get("codex", {}).get("enabled", True)
    return config_bool(value, True)


def display_status_board_enabled(display: Dict[str, Any]) -> bool:
    """Return the status-board display flag, accepting the legacy key."""
    if "show_status_board" in display:
        return config_bool(display.get("show_status_board"), False)
    return config_bool(display.get("show_vibe_board"), True)


# Global config
config = load_config()


# ============================================================================
# Collaboration Status
# ============================================================================

def configured_api_token() -> str:
    """Return the optional API write token."""
    return str(config.get("security", {}).get("api_token", "")).strip()


def public_config() -> Dict[str, Any]:
    """Return configuration safe to expose through the read-only config API."""
    safe_config = copy.deepcopy(config)
    token = str(safe_config.get("security", {}).get("api_token", "")).strip()
    if token:
        safe_config.setdefault("security", {})["api_token"] = "<configured>"
    return safe_config


def tokens_match(expected: str, supplied: str) -> bool:
    """Compare API tokens without accepting empty configured tokens."""
    return bool(expected) and supplied == expected


def redact_sensitive_url(value: str) -> str:
    """Redact sensitive query parameters before logging request targets."""
    parsed = urlparse(str(value))
    if not parsed.query:
        return str(value)

    query_items = []
    changed = False
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() == "token":
            query_items.append((key, "REDACTED"))
            changed = True
        else:
            query_items.append((key, item_value))

    if not changed:
        return str(value)
    return urlunparse(parsed._replace(query=urlencode(query_items, doseq=True)))


def redact_sensitive_request_line(request_line: str) -> str:
    """Redact sensitive query parameters from an HTTP request line."""
    parts = str(request_line).split(" ", 2)
    if len(parts) < 2:
        return str(request_line)
    parts[1] = redact_sensitive_url(parts[1])
    return " ".join(parts)


def status_stale_after_seconds() -> int:
    """Return the heartbeat freshness threshold."""
    value = config.get("status", {}).get("stale_after_seconds")
    if value is None:
        value = config.get("vibe", {}).get("stale_after_seconds", 900)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 900


def codex_session_file_limit(value: Any = None) -> int:
    """Return a safe limit for recent Codex session files to scan."""
    if value is None:
        value = config.get("codex", {}).get("session_file_limit", 10)
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 10
    return max(1, min(100, limit))


def vibe_stale_after_seconds() -> int:
    """Compatibility wrapper for the old status freshness helper name."""
    return status_stale_after_seconds()


def is_vibe_status_stale(status: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Return true when the displayed status has not been updated recently."""
    return is_status_stale(status, status_stale_after_seconds(), now)


def _load_vibe_status_unlocked() -> Dict[str, Any]:
    """Load persisted status while the caller owns status_lock."""
    status_file = STATUS_FILE if STATUS_FILE.exists() else STATUS_FILE_LEGACY
    try:
        if status_file.exists():
            with open(status_file, "r", encoding="utf-8") as f:
                return normalize_vibe_status(json.load(f))
    except Exception as e:
        logger.warning(f"Failed to load vibe status: {e}")
    return default_vibe_status()


def load_vibe_status() -> Dict[str, Any]:
    """Load the persisted status from disk (new name first, legacy fallback)."""
    with status_lock:
        return _load_vibe_status_unlocked()


def _save_vibe_status_unlocked(status: Dict[str, Any]) -> bool:
    """Persist status while the caller owns status_lock."""
    try:
        normalized = normalize_vibe_status(status)
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Failed to save vibe status: {e}")
        return False


def save_vibe_status(status: Dict[str, Any]) -> bool:
    """Persist status to disk."""
    with status_lock:
        return _save_vibe_status_unlocked(status)


def update_vibe_status(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge an API patch into the current status and persist it atomically."""
    if not isinstance(patch, dict):
        raise ValueError("JSON body must be an object")

    with status_lock:
        status = merge_status_patch(_load_vibe_status_unlocked(), patch)
        if not _save_vibe_status_unlocked(status):
            raise OSError("failed to save vibe status")
        return _load_vibe_status_unlocked()


def load_vibe_presets() -> list:
    """Load built-in vibe preset summaries for API consumers."""
    presets = []
    for name in PRESET_NAMES:
        path = PRESET_DIR / f"{name}.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load vibe preset {name}: {e}")
            continue
        if not isinstance(payload, dict):
            logger.warning(f"Vibe preset {name} is not a JSON object")
            continue

        presets.append({
            "name": name,
            "state": _as_clean_text(payload.get("state")),
            "current_task": _as_clean_text(payload.get("current_task")),
            "next_action": _as_clean_text(payload.get("next_action")),
            "payload": payload,
        })
    return presets


# ============================================================================
# Codex Usage Data
# ============================================================================

class CodexUsage:
    """Represents Codex usage data."""
    
    def __init__(self):
        self.five_hour_percent_left: int = -1
        self.five_hour_reset: str = ""
        self.weekly_percent_left: int = -1
        self.weekly_reset: str = ""
        self.credits: str = ""
        self.plan_type: str = ""
        self.last_updated: str = ""
        self.source: str = ""  # "cli-rpc" or "session"
        self.error: str = ""
        self.local_token_usage: Dict[str, Any] = default_local_token_usage()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "five_hour_percent_left": self.five_hour_percent_left,
            "five_hour_reset": self.five_hour_reset,
            "weekly_percent_left": self.weekly_percent_left,
            "weekly_reset": self.weekly_reset,
            "credits": self.credits,
            "plan_type": self.plan_type,
            "source": self.source,
            "last_updated": self.last_updated,
            "error": self.error,
            "local_token_usage": self.local_token_usage,
        }


TOKEN_USAGE_FIELDS = [
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
]


def empty_token_window(hours: int) -> Dict[str, Any]:
    return {
        "window_hours": hours,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
        "cache_hit_percent": -1,
        "event_count": 0,
        "session_count": 0,
        "first_seen": "",
        "last_seen": "",
    }


def default_local_token_usage() -> Dict[str, Any]:
    return {
        "source": "codex-session-files",
        "note": "本机 Codex 会话文件统计，不代表跨设备账户总量",
        "last_scanned_at": "",
        "windows": {
            "24h": empty_token_window(24),
            "7d": empty_token_window(24 * 7),
        },
    }


def parse_codex_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def add_token_usage(window: Dict[str, Any], usage: Dict[str, Any], event_time: datetime, session_id: str):
    for field in TOKEN_USAGE_FIELDS:
        value = usage.get(field, 0)
        if isinstance(value, (int, float)):
            window[field] += int(value)
    window["event_count"] += 1
    window.setdefault("_sessions", set()).add(session_id)

    display_time = event_time.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    if not window["first_seen"] or display_time < window["first_seen"]:
        window["first_seen"] = display_time
    if not window["last_seen"] or display_time > window["last_seen"]:
        window["last_seen"] = display_time


def finalize_token_window(window: Dict[str, Any]):
    sessions = window.pop("_sessions", set())
    window["session_count"] = len(sessions)
    input_tokens = window.get("input_tokens", 0)
    cached_tokens = window.get("cached_input_tokens", 0)
    if input_tokens > 0:
        window["cache_hit_percent"] = round(cached_tokens * 100 / input_tokens, 1)


def compute_local_token_usage(
    codex_home: Optional[Path] = None,
    now: Optional[datetime] = None,
    session_file_limit: Optional[int] = None,
) -> Dict[str, Any]:
    result = default_local_token_usage()
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_utc = now_utc.astimezone(timezone.utc)
    result["last_scanned_at"] = now_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    home = codex_home or (Path.home() / ".codex")
    session_dirs = [
        home / "sessions",
        home / "archived_sessions",
    ]
    cutoffs = {
        "24h": now_utc - timedelta(hours=24),
        "7d": now_utc - timedelta(days=7),
    }

    session_files = []
    for session_dir in session_dirs:
        if not session_dir.exists():
            continue
        session_files.extend(session_dir.rglob("*.jsonl"))

    session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    for session_file in session_files[:codex_session_file_limit(session_file_limit)]:
        try:
            if datetime.fromtimestamp(session_file.stat().st_mtime, tz=timezone.utc) < cutoffs["7d"]:
                continue
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") != "event_msg":
                        continue
                    payload = event.get("payload", {})
                    if payload.get("type") != "token_count":
                        continue
                    event_time = parse_codex_timestamp(event.get("timestamp"))
                    if not event_time:
                        continue
                    last_usage = payload.get("info", {}).get("last_token_usage", {})
                    if not isinstance(last_usage, dict):
                        continue
                    for key, cutoff in cutoffs.items():
                        if event_time >= cutoff:
                            add_token_usage(
                                result["windows"][key],
                                last_usage,
                                event_time,
                                str(session_file),
                            )
        except Exception as e:
            logger.warning(f"Error reading token usage from {session_file}: {e}")

    for window in result["windows"].values():
        finalize_token_window(window)
    return result


def attach_local_token_usage(usage: CodexUsage) -> CodexUsage:
    try:
        usage.local_token_usage = compute_local_token_usage()
    except Exception as e:
        logger.warning(f"Failed to compute local token usage: {e}")
        usage.local_token_usage = default_local_token_usage()
        usage.local_token_usage["error"] = str(e)
    return usage


def find_codex_binary() -> Optional[str]:
    """Find the codex binary in PATH."""
    try:
        result = subprocess.run(
            ["which", "codex"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            logger.debug(f"Found codex binary at: {path}")
            return path
    except Exception as e:
        logger.warning(f"Error finding codex binary: {e}")
    return None


def fetch_codex_status_cli() -> CodexUsage:
    """Fetch Codex usage via JSON-RPC through codex app-server."""
    usage = CodexUsage()
    
    codex_path = find_codex_binary()
    if not codex_path:
        usage.error = "PATH 中找不到 codex"
        logger.error(usage.error)
        return usage
    
    process = None
    try:
        logger.info("Starting codex app-server for RPC...")
        
        # Start codex app-server process
        process = subprocess.Popen(
            [codex_path, "-s", "read-only", "-a", "untrusted", "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Buffer for stdout lines
        stdout_lines = []
        stdout_lock = threading.Lock()
        
        def read_stdout():
            """Read stdout lines in a separate thread."""
            for line in iter(process.stdout.readline, b''):
                with stdout_lock:
                    stdout_lines.append(line)
        
        reader_thread = threading.Thread(target=read_stdout, daemon=True)
        reader_thread.start()
        
        request_counter = [0]
        
        def send_request(method: str, params: Optional[Dict] = None, timeout: float = 3.0) -> Optional[Dict]:
            """Send a JSON-RPC request and wait for response."""
            request_counter[0] += 1
            request_id = request_counter[0]
            request = {
                "id": request_id,
                "method": method,
                "params": params or {}
            }
            
            request_json = json.dumps(request) + "\n"
            process.stdin.write(request_json.encode())
            process.stdin.flush()
            
            logger.debug(f"Sent RPC request: {method} (id={request_id})")
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                with stdout_lock:
                    for line in stdout_lines:
                        try:
                            message = json.loads(line.decode().strip())
                            if "id" not in message:
                                continue
                            if message["id"] == request_id:
                                logger.debug(f"Received RPC response for: {method}")
                                return message
                        except json.JSONDecodeError:
                            continue
                time.sleep(0.1)
            
            logger.warning(f"RPC request timeout: {method}")
            return None
        
        def send_notification(method: str, params: Optional[Dict] = None):
            """Send a JSON-RPC notification (no response expected)."""
            notification = {
                "method": method,
                "params": params or {}
            }
            notification_json = json.dumps(notification) + "\n"
            process.stdin.write(notification_json.encode())
            process.stdin.flush()
            logger.debug(f"Sent RPC notification: {method}")
        
        # Initialize
        init_response = send_request("initialize", {
            "clientInfo": {
                "name": "inkdash",
                "version": "1.0.0"
            }
        }, timeout=5.0)
        
        if not init_response or "error" in init_response:
            error_msg = init_response.get("error", {}).get("message", "Unknown error") if init_response else "No response"
            usage.error = f"初始化 Codex RPC 失败：{error_msg}"
            logger.error(usage.error)
            process.terminate()
            return usage
        
        # Send initialized notification
        send_notification("initialized")
        
        # Fetch rate limits
        limits_response = send_request("account/rateLimits/read", timeout=5.0)
        
        # Clean up
        process.terminate()
        process = None
        
        if not limits_response or "error" in limits_response:
            error_msg = limits_response.get("error", {}).get("message", "Unknown error") if limits_response else "No response"
            usage.error = f"读取 Codex 用量失败：{error_msg}"
            logger.error(usage.error)
            return usage
        
        # Parse response
        usage.source = "cli-rpc"
        usage.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        result = limits_response.get("result", {})
        rate_limits = result.get("rateLimits", {})
        
        # Parse primary (5h limit)
        primary = rate_limits.get("primary", {})
        if primary:
            used_percent = primary.get("usedPercent", 0)
            usage.five_hour_percent_left = 100 - int(used_percent)
            
            resets_at = primary.get("resetsAt")
            if resets_at:
                reset_dt = datetime.fromtimestamp(resets_at)
                usage.five_hour_reset = reset_dt.strftime("%H:%M")
        
        # Parse secondary (weekly limit)
        secondary = rate_limits.get("secondary", {})
        if secondary:
            used_percent = secondary.get("usedPercent", 0)
            usage.weekly_percent_left = 100 - int(used_percent)
            
            resets_at = secondary.get("resetsAt")
            if resets_at:
                reset_dt = datetime.fromtimestamp(resets_at)
                usage.weekly_reset = reset_dt.strftime("%m-%d %H:%M")
        
        # Parse credits
        credits = rate_limits.get("credits", {})
        if credits:
            balance = credits.get("balance")
            if balance:
                usage.credits = f"余额：{balance}"
            elif credits.get("unlimited"):
                usage.credits = "余额：无限"
        
        # Parse plan type
        plan_type = rate_limits.get("planType")
        if plan_type:
            usage.plan_type = plan_type.capitalize()
        
        logger.info(f"Codex usage fetched via RPC: 5h={usage.five_hour_percent_left}%, weekly={usage.weekly_percent_left}%")
        return usage
        
    except Exception as e:
        if process:
            try:
                process.terminate()
            except:
                pass
        usage.error = f"Codex RPC 出错：{str(e)}"
        logger.exception("Exception in fetch_codex_status_cli")
        return usage


def fetch_codex_status_session() -> CodexUsage:
    """Fetch Codex usage from local session files (fallback)."""
    usage = CodexUsage()
    usage.source = "session"
    usage.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    logger.info("Fetching Codex usage from session files...")
    
    codex_home = Path.home() / ".codex"
    session_dirs = [
        codex_home / "sessions",
        codex_home / "archived_sessions"
    ]
    
    session_files = []
    for session_dir in session_dirs:
        if session_dir.exists():
            for jsonl_file in session_dir.rglob("*.jsonl"):
                session_files.append(jsonl_file)
    
    if not session_files:
        usage.error = "没有找到 Codex 会话文件"
        logger.warning(usage.error)
        return usage
    
    logger.debug(f"Found {len(session_files)} session files")
    
    # Sort by modification time (newest first)
    session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    # Limit the number of files to check
    for session_file in session_files[:codex_session_file_limit()]:
        try:
            with open(session_file, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        if (event.get("type") == "event_msg" and 
                            event.get("payload", {}).get("type") == "token_count"):
                            
                            rate_limits = event.get("payload", {}).get("rate_limits", {})
                            primary = rate_limits.get("primary", {})
                            secondary = rate_limits.get("secondary", {})
                            
                            if primary.get("window_minutes") or secondary.get("window_minutes"):
                                usage.five_hour_percent_left = 100 - int(primary.get("used_percent", 0))
                                usage.weekly_percent_left = 100 - int(secondary.get("used_percent", 0))
                                
                                if primary.get("resets_at"):
                                    reset_dt = datetime.fromtimestamp(primary["resets_at"])
                                    usage.five_hour_reset = reset_dt.strftime("%H:%M")
                                
                                if secondary.get("resets_at"):
                                    reset_dt = datetime.fromtimestamp(secondary["resets_at"])
                                    usage.weekly_reset = reset_dt.strftime("%m-%d %H:%M")
                                
                                plan_type = rate_limits.get("plan_type", "")
                                if plan_type:
                                    usage.plan_type = plan_type.capitalize()
                                
                                logger.info(f"Codex usage fetched from session: 5h={usage.five_hour_percent_left}%, weekly={usage.weekly_percent_left}%")
                                return usage
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Error reading session file {session_file}: {e}")
            continue
    
    usage.error = "会话文件中没有可用的 Codex 用量数据"
    logger.warning(usage.error)
    return usage


def fetch_codex_usage() -> CodexUsage:
    """Fetch Codex usage based on configured source."""
    if not codex_enabled_flag():
        usage = CodexUsage()
        usage.source = "disabled"
        usage.last_updated = now_display()
        usage.error = "Codex 监控已关闭"
        return attach_local_token_usage(usage)

    source = config.get("codex", {}).get("source", "auto")
    
    if source == "session":
        return attach_local_token_usage(fetch_codex_status_session())
    elif source == "cli":
        return attach_local_token_usage(fetch_codex_status_cli())
    else:  # auto
        # Try CLI first
        usage = fetch_codex_status_cli()
        if not usage.error and (usage.five_hour_percent_left >= 0 or usage.weekly_percent_left >= 0):
            return attach_local_token_usage(usage)
        
        logger.info("CLI fetch failed, falling back to session files")
        return attach_local_token_usage(fetch_codex_status_session())


# ============================================================================
# Global Cache
# ============================================================================

usage_cache = CodexUsage()
cache_lock = threading.Lock()
status_lock = threading.RLock()
last_fetch_time = 0
fetch_count = 0


def refresh_cache():
    """Refresh the usage cache."""
    global usage_cache, last_fetch_time, fetch_count
    
    while True:
        try:
            interval = refresh_interval_seconds()
            
            new_usage = fetch_codex_usage()
            with cache_lock:
                usage_cache = new_usage
                last_fetch_time = time.time()
                fetch_count += 1
            
            if new_usage.error:
                logger.warning(f"Cache refresh completed with error: {new_usage.error}")
            else:
                logger.info(f"Cache refreshed: 5h={new_usage.five_hour_percent_left}%, weekly={new_usage.weekly_percent_left}%")
        except Exception as e:
            logger.exception("Error in refresh_cache")
        
        time.sleep(interval)


# ============================================================================
# HTML Templates
# ============================================================================

def generate_main_html(
    usage: CodexUsage,
    vibe_status: Dict[str, Any],
    layout_mode: Optional[str] = None,
    text_scale_percent: Optional[int] = None,
) -> str:
    """Generate main dashboard HTML."""
    def h(value: Any) -> str:
        return escape(str(value), quote=True)

    def percent(value: int) -> int:
        return max(0, min(100, value if value >= 0 else 0))

    def render_badges(items: list, empty_text: str) -> str:
        if not items:
            return f'<span class="muted">{h(empty_text)}</span>'
        return "".join(f'<span class="badge">{h(item)}</span>' for item in items)

    def render_events(events: list) -> str:
        rows = []
        for event in events[-MAX_EVENT_ITEMS:]:
            if not isinstance(event, dict):
                continue
            rows.append(f'''
            <div class="event-row">
                <span class="event-time">{h(event.get("time", ""))}</span>
                <span class="event-text">{h(event.get("text", ""))}</span>
            </div>''')
        if not rows:
            return '<div class="muted">暂无事件</div>'
        return "".join(rows)

    def token_window(name: str, hours: int) -> Dict[str, Any]:
        local_usage = usage.local_token_usage if isinstance(usage.local_token_usage, dict) else {}
        windows = local_usage.get("windows", {})
        if not isinstance(windows, dict):
            return empty_token_window(hours)
        window = windows.get(name, {})
        return window if isinstance(window, dict) else empty_token_window(hours)

    def token_count(value: Any) -> str:
        try:
            return f"{int(value):,} tokens"
        except (TypeError, ValueError):
            return "0 tokens"

    def cache_hit(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "暂无"
        if number < 0:
            return "暂无"
        return f"{number:.1f}%"

    def scaled(px: int) -> str:
        return f"{round(px * text_scale_ratio)}px"

    def layout_link(mode: str) -> str:
        active_class = " active" if mode == layout_mode else ""
        return f'<a class="layout-option{active_class}" href="/layout?mode={h(mode)}">{h(LAYOUT_MODE_LABELS[mode])}</a>'

    def text_scale_link(scale: int) -> str:
        active_class = " active" if scale == text_scale_percent else ""
        return f'<a class="layout-option{active_class}" href="/text-scale?scale={scale}">{scale}%</a>'

    token_24h = token_window("24h", 24)
    token_7d = token_window("7d", 24 * 7)
    five_hour_percent = percent(usage.five_hour_percent_left)
    weekly_percent = percent(usage.weekly_percent_left)
    five_hour_reset = usage.five_hour_reset if usage.five_hour_reset else "未知"
    weekly_reset = usage.weekly_reset if usage.weekly_reset else "未知"
    plan_type = usage.plan_type if usage.plan_type else "未知"
    credits = usage.credits if usage.credits else "未知"
    source = usage.source if usage.source else "未知"
    last_updated = usage.last_updated if usage.last_updated else "从未更新"
    refresh_ms = page_refresh_seconds() * 1000
    layout_mode = normalize_layout_mode(layout_mode or current_layout_mode())
    layout_label = LAYOUT_MODE_LABELS.get(layout_mode, "自动")
    text_scale_percent = normalize_text_scale(
        text_scale_percent if text_scale_percent is not None else current_text_scale()
    )
    text_scale_ratio = text_scale_percent / 100
    layout_switch = "".join(layout_link(mode) for mode in LAYOUT_MODES)
    text_scale_options = sorted(set(TEXT_SCALE_QUICK_VALUES + (text_scale_percent,)))
    text_scale_switch = "".join(text_scale_link(scale) for scale in text_scale_options)

    display = config.get("display", {})

    vibe_board = ""
    if display_status_board_enabled(display):
        blockers = _as_text_list(vibe_status.get("blockers"))
        participants = _as_text_list(vibe_status.get("participants"))
        events = _as_event_list(vibe_status.get("events"))
        stale = is_vibe_status_stale(vibe_status)
        heartbeat_label = "可能过期" if stale else "心跳正常"
        heartbeat_class = "stale-pill" if stale else "fresh-pill"
        vibe_board = f'''
    <section class="panel vibe-panel">
        <div class="panel-title-row">
            <h2>{h(vibe_status.get("title", "状态看板"))}</h2>
            <div class="pill-group">
                <span class="state-pill">{h(vibe_status.get("state", "待更新"))}</span>
                <span class="{heartbeat_class}">{heartbeat_label}</span>
            </div>
        </div>

        <div class="main-objective">{h(vibe_status.get("objective", ""))}</div>

        <div class="fact-grid">
            <div class="fact">
                <div class="fact-label">项目</div>
                <div class="fact-value">{h(vibe_status.get("project", ""))}</div>
            </div>
            <div class="fact">
                <div class="fact-label">分支</div>
                <div class="fact-value">{h(vibe_status.get("branch", ""))}</div>
            </div>
            <div class="fact">
                <div class="fact-label">更新时间</div>
                <div class="fact-value">{h(vibe_status.get("updated_at", ""))}</div>
            </div>
        </div>

        <div class="focus-row">
            <div>
                <div class="section-label">当前任务</div>
                <div class="large-text">{h(vibe_status.get("current_task", ""))}</div>
            </div>
            <div>
                <div class="section-label">下一步</div>
                <div class="large-text">{h(vibe_status.get("next_action", ""))}</div>
            </div>
        </div>

        <div class="tag-row">
            <div>
                <div class="section-label">参与者</div>
                <div>{render_badges(participants, "未指定")}</div>
            </div>
            <div>
                <div class="section-label">阻塞项</div>
                <div>{render_badges(blockers, "无")}</div>
            </div>
        </div>

        <div class="section-label">最近事件</div>
        <div class="events">{render_events(events)}</div>
    </section>'''

    account_info_rows = ""
    if display_flag(display, "show_plan_type"):
        account_info_rows += f'''
        <div class="info-row">
            <span class="info-label">套餐</span>
            <span class="info-value">{h(plan_type)}</span>
        </div>'''

    if display_flag(display, "show_credits"):
        account_info_rows += f'''
        <div class="info-row">
            <span class="info-label">余额</span>
            <span class="info-value">{h(credits)}</span>
        </div>'''

    if display_flag(display, "show_data_source"):
        account_info_rows += f'''
        <div class="info-row">
            <span class="info-label">数据来源</span>
            <span class="info-value">{h(source)}</span>
        </div>'''

    if display_flag(display, "show_last_updated"):
        account_info_rows += f'''
        <div class="info-row">
            <span class="info-label">更新时间</span>
            <span class="info-value">{h(last_updated)}</span>
        </div>'''

    error_section = ""
    if usage.error:
        error_section = f'''
    <section class="panel">
        <h2>提示</h2>
        <div class="notice">{h(usage.error)}</div>
    </section>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="{refresh_ms // 1000}">
    <title>InkDash</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #ffffff;
            color: #000000;
            padding: 18px;
            max-width: 1040px;
            margin: 0 auto;
            line-height: 1.35;
        }}

        .layout-portrait {{
            max-width: 820px;
        }}

        .layout-landscape {{
            max-width: 1180px;
        }}

        .header {{
            position: relative;
            padding-bottom: 14px;
            margin-bottom: 18px;
            border-bottom: 3px solid #000000;
        }}

        .header h1 {{
            font-size: {scaled(44)};
            line-height: 1;
            font-weight: 800;
        }}

        .subtitle {{
            margin-top: 8px;
            font-size: {scaled(20)};
            color: #333333;
        }}

        .header-actions {{
            position: absolute;
            top: 0;
            right: 0;
            display: flex;
            align-items: flex-start;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }}

        .settings-btn {{
            background: #000000;
            color: #ffffff;
            border: 2px solid #000000;
            padding: 9px 14px;
            font-size: {scaled(18)};
            text-decoration: none;
        }}

        .layout-switch {{
            display: flex;
            border: 2px solid #000000;
            background: #ffffff;
        }}

        .layout-option {{
            display: inline-block;
            min-width: 58px;
            color: #000000;
            padding: 9px 10px;
            border-right: 1px solid #000000;
            font-size: {scaled(18)};
            font-weight: 700;
            text-align: center;
            text-decoration: none;
        }}

        .layout-option:last-child {{
            border-right: 0;
        }}

        .layout-option.active {{
            color: #ffffff;
            background: #000000;
        }}

        .dashboard-layout {{
            /* block fallback for old Kindle WebKit */
            display: block;
            gap: 18px;
        }}

        @supports (display: grid) {{
            .dashboard-layout {{
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: 18px;
                align-items: start;
            }}
        }}

        .usage-stack {{
            display: block;
        }}

        @supports (display: grid) {{
            .usage-stack {{
                display: grid;
                gap: 18px;
                min-width: 0;
            }}
        }}

        .dashboard-layout > .usage-stack:only-child {{
            grid-column: 1 / -1;
        }}

        .dashboard-layout > .panel,
        .usage-stack .panel {{
            margin-bottom: 0;
        }}

        .panel {{
            border: 2px solid #000000;
            border-radius: 4px;
            padding: 18px;
            margin-bottom: 18px;
            background: #ffffff;
        }}

        .panel h2 {{
            font-size: {scaled(28)};
            margin-bottom: 14px;
        }}

        .panel-title-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            border-bottom: 2px solid #000000;
            padding-bottom: 10px;
            margin-bottom: 14px;
        }}

        .state-pill {{
            display: inline-block;
            min-width: 96px;
            text-align: center;
            border: 2px solid #000000;
            padding: 6px 12px;
            font-size: {scaled(20)};
            font-weight: 700;
            background: #eeeeee;
        }}

        .pill-group {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }}

        .fresh-pill,
        .stale-pill {{
            display: inline-block;
            min-width: 96px;
            text-align: center;
            border: 2px solid #000000;
            padding: 6px 12px;
            font-size: {scaled(20)};
            font-weight: 700;
        }}

        .fresh-pill {{
            background: #ffffff;
        }}

        .stale-pill {{
            color: #ffffff;
            background: #000000;
        }}

        .main-objective {{
            font-size: {scaled(30)};
            font-weight: 800;
            margin-bottom: 16px;
            word-break: break-word;
        }}

        .fact-grid {{
            display: block;
        }}

        .fact-grid .fact {{
            min-height: 86px;
            border-right: 1px solid #000000;
            border-bottom: 1px solid #000000;
            padding: 10px;
        }}

        @supports (display: grid) {{
            .fact-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                border-top: 1px solid #000000;
                border-left: 1px solid #000000;
                margin-bottom: 16px;
            }}

            .fact-grid .fact {{
                border-right: 1px solid #000000;
                border-bottom: 1px solid #000000;
                padding: 10px;
            }}
        }}

        .fact-label,
        .section-label {{
            font-size: {scaled(15)};
            color: #333333;
            font-weight: 700;
            margin-bottom: 6px;
        }}

        .fact-value {{
            font-size: {scaled(22)};
            font-weight: 700;
            word-break: break-word;
        }}

        .focus-row,
        .tag-row {{
            display: block;
        }}

        @supports (display: grid) {{
            .focus-row,
            .tag-row {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 14px;
                margin-bottom: 16px;
            }}
        }}

        .large-text {{
            min-height: 86px;
            border: 1px solid #000000;
            padding: 12px;
            font-size: {scaled(24)};
            font-weight: 700;
            word-break: break-word;
        }}

        .badge {{
            display: inline-block;
            border: 1px solid #000000;
            padding: 5px 9px;
            margin: 0 6px 6px 0;
            font-size: {scaled(18)};
            font-weight: 700;
            background: #f2f2f2;
        }}

        .muted {{
            color: #555555;
            font-size: {scaled(18)};
        }}

        .events {{
            border-top: 1px solid #000000;
        }}

        .event-row {{
            display: block;
            padding: 9px 0;
            border-bottom: 1px solid #cccccc;
        }}

        @supports (display: grid) {{
            .event-row {{
                display: grid;
                grid-template-columns: 180px 1fr;
                gap: 12px;
                padding: 9px 0;
                border-bottom: 1px solid #cccccc;
            }}
        }}

        .event-time {{
            font-size: {scaled(16)};
            color: #333333;
            font-weight: 700;
        }}

        .event-text {{
            font-size: {scaled(20)};
            font-weight: 700;
            word-break: break-word;
        }}

        .limit-row {{
            display: block;
            padding: 12px 0;
            border-bottom: 1px solid #cccccc;
        }}

        @supports (display: grid) {{
            .limit-row {{
                display: grid;
                grid-template-columns: 180px 1fr 110px;
                gap: 14px;
                align-items: center;
                padding: 12px 0;
                border-bottom: 1px solid #cccccc;
            }}
        }}

        .limit-label {{
            font-size: {scaled(21)};
            font-weight: 800;
        }}

        .limit-reset {{
            font-size: {scaled(15)};
            color: #333333;
            margin-top: 4px;
        }}

        .limit-bar {{
            height: 34px;
            background: #eeeeee;
            border: 2px solid #000000;
            overflow: hidden;
        }}

        .limit-bar-fill {{
            height: 100%;
            background: #000000;
        }}

        .limit-percent {{
            font-size: {scaled(23)};
            font-weight: 800;
            text-align: right;
        }}

        .token-block {{
            margin-top: 16px;
            padding-top: 14px;
            border-top: 2px solid #000000;
        }}

        .token-row {{
            display: block;
            padding: 9px 0;
            border-bottom: 1px solid #cccccc;
        }}

        @supports (display: grid) {{
            .token-row {{
                display: grid;
                grid-template-columns: 150px 1fr 180px;
                gap: 12px;
                align-items: center;
                padding: 9px 0;
                border-bottom: 1px solid #cccccc;
            }}
        }}

        .token-window,
        .token-value,
        .token-cache {{
            font-size: {scaled(19)};
            font-weight: 700;
            word-break: break-word;
        }}

        .token-value {{
            font-size: {scaled(22)};
            font-weight: 800;
        }}

        .token-note {{
            margin-top: 9px;
            color: #333333;
            font-size: {scaled(15)};
            font-weight: 700;
        }}

        .info-row {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            padding: 8px 0;
            border-bottom: 1px solid #cccccc;
        }}

        .info-label,
        .info-value {{
            font-size: {scaled(20)};
            font-weight: 700;
            word-break: break-word;
        }}

        .notice {{
            border: 1px solid #000000;
            background: #f4f4f4;
            padding: 10px;
            font-size: {scaled(19)};
            font-weight: 700;
            word-break: break-word;
        }}

        .footer {{
            text-align: center;
            margin-top: 18px;
            padding-top: 12px;
            border-top: 3px solid #000000;
            color: #333333;
            font-size: {scaled(16)};
        }}

        @supports (display: grid) {{
            .layout-landscape .dashboard-layout {{
                grid-template-columns: minmax(0, 1.15fr) minmax(340px, 0.85fr);
            }}
        }}

        .layout-landscape .panel {{
            margin-bottom: 0;
        }}

        @media (orientation: landscape) and (min-width: 860px), (min-width: 1100px) {{
            .layout-auto {{
                max-width: 1180px;
            }}

            @supports (display: grid) {{
                .layout-auto .dashboard-layout {{
                    grid-template-columns: minmax(0, 1.15fr) minmax(340px, 0.85fr);
                }}
            }}

            .layout-auto .panel {{
                margin-bottom: 0;
            }}
        }}

        @media (max-width: 720px) {{
            body {{
                padding: 12px;
            }}

            .header h1 {{
                font-size: {scaled(34)};
            }}

            .header-actions {{
                position: static;
                margin-top: 12px;
                justify-content: flex-start;
            }}

            .settings-btn,
            .layout-option {{
                font-size: {scaled(16)};
                padding: 8px 10px;
            }}

            @supports (display: grid) {{
                .fact-grid,
                .focus-row,
                .tag-row,
                .limit-row,
                .token-row,
                .event-row {{
                    grid-template-columns: 1fr;
                }}
            }}

            .main-objective {{
                font-size: {scaled(24)};
            }}
        }}

        @media (max-width: 720px) {{
            .layout-landscape {{
                max-width: 1180px;
            }}

            @supports (display: grid) {{
                .layout-landscape .dashboard-layout {{
                    grid-template-columns: 1fr;
                }}

                .layout-landscape .fact-grid {{
                    grid-template-columns: 1fr 1fr;
                }}

                .layout-landscape .focus-row,
                .layout-landscape .tag-row {{
                    grid-template-columns: 1fr;
                }}

                .layout-landscape .limit-row {{
                    grid-template-columns: 1fr;
                }}

                .layout-landscape .token-row {{
                    grid-template-columns: 1fr;
                }}

                .layout-landscape .event-row {{
                    grid-template-columns: 1fr;
                }}
            }}

            .layout-landscape .header-actions {{
                position: static;
                margin-top: 12px;
                justify-content: flex-start;
            }}

            .layout-landscape .settings-btn,
            .layout-landscape .layout-option {{
                font-size: {scaled(16)};
                padding: 8px 10px;
            }}
        }}
    </style>
</head>
<body class="layout-{h(layout_mode)}" style="--text-scale: {text_scale_ratio:.2f};">
    <header class="header">
        <h1>InkDash</h1>
        <div class="subtitle">Codex 用量常亮状态面板 · {h(layout_label)}布局 · {text_scale_percent}%字号</div>
        <div class="header-actions">
            <nav class="layout-switch" aria-label="布局模式">
                {layout_switch}
            </nav>
            <nav class="layout-switch" aria-label="字号比例">
                {text_scale_switch}
            </nav>
            <a href="/settings" class="settings-btn">设置</a>
        </div>
    </header>

    <main class="dashboard-layout">
        {vibe_board}

        <div class="usage-stack">
            <section class="panel">
                <h2>Codex 用量</h2>

                <div class="limit-row">
                    <div>
                        <div class="limit-label">5 小时额度</div>
                        <div class="limit-reset">重置：{h(five_hour_reset)}</div>
                    </div>
                    <div class="limit-bar">
                        <div class="limit-bar-fill" style="width: {five_hour_percent}%"></div>
                    </div>
                    <div class="limit-percent">{five_hour_percent}%</div>
                </div>

                <div class="limit-row">
                    <div>
                        <div class="limit-label">周额度</div>
                        <div class="limit-reset">重置：{h(weekly_reset)}</div>
                    </div>
                    <div class="limit-bar">
                        <div class="limit-bar-fill" style="width: {weekly_percent}%"></div>
                    </div>
                    <div class="limit-percent">{weekly_percent}%</div>
                </div>

                <div class="token-block">
                    <div class="section-label">本机 Token 消耗</div>
                    <div class="token-row">
                        <span class="token-window">近 24 小时</span>
                        <span class="token-value">{token_count(token_24h.get("total_tokens"))}</span>
                        <span class="token-cache">缓存命中 {cache_hit(token_24h.get("cache_hit_percent"))}</span>
                    </div>
                    <div class="token-row">
                        <span class="token-window">近 7 天</span>
                        <span class="token-value">{token_count(token_7d.get("total_tokens"))}</span>
                        <span class="token-cache">缓存命中 {cache_hit(token_7d.get("cache_hit_percent"))}</span>
                    </div>
                    <div class="token-note">Token 数来自本机 Codex 会话文件；额度百分比来自服务器侧 RPC。</div>
                </div>
            </section>

            <section class="panel">
                <h2>账户信息</h2>
                {account_info_rows}
            </section>

            {error_section}
        </div>
    </main>

    <footer class="footer">
        <div>页面每 {refresh_ms // 1000} 秒自动刷新</div>
        <div>InkDash</div>
    </footer>
</body>
</html>'''

    return html


def generate_status_text(
    usage: CodexUsage,
    vibe_status: Dict[str, Any],
    layout_mode: Optional[str] = None,
    text_scale_percent: Optional[int] = None,
) -> str:
    """Generate a plain-text fallback view for old Kindle browsers and scripts."""
    def text(value: Any, fallback: str = "未指定") -> str:
        value = str(value).strip() if value is not None else ""
        return value if value else fallback

    def percent(value: int) -> str:
        if value < 0:
            return "未知"
        return f"{max(0, min(100, value))}%"

    def token_window(name: str, hours: int) -> Dict[str, Any]:
        local_usage = usage.local_token_usage if isinstance(usage.local_token_usage, dict) else {}
        windows = local_usage.get("windows", {})
        if not isinstance(windows, dict):
            return empty_token_window(hours)
        window = windows.get(name, {})
        return window if isinstance(window, dict) else empty_token_window(hours)

    def token_count(value: Any) -> str:
        try:
            return f"{int(value):,} tokens"
        except (TypeError, ValueError):
            return "0 tokens"

    def cache_hit(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "暂无"
        if number < 0:
            return "暂无"
        return f"{number:.1f}%"

    blockers = _as_text_list(vibe_status.get("blockers"))
    participants = _as_text_list(vibe_status.get("participants"))
    events = _as_event_list(vibe_status.get("events"))
    heartbeat = "可能过期" if is_vibe_status_stale(vibe_status) else "正常"
    token_24h = token_window("24h", 24)
    token_7d = token_window("7d", 24 * 7)
    layout_label = LAYOUT_MODE_LABELS.get(
        normalize_layout_mode(layout_mode or current_layout_mode()),
        "自动",
    )
    text_scale_percent = normalize_text_scale(
        text_scale_percent if text_scale_percent is not None else current_text_scale()
    )

    lines = [
        "InkDash",
        "=" * 20,
        f"布局模式：{layout_label}",
        f"字号比例：{text_scale_percent}%",
        f"状态：{text(vibe_status.get('state'), '待更新')}",
        f"目标：{text(vibe_status.get('objective'))}",
        f"项目：{text(vibe_status.get('project'))}",
        f"分支：{text(vibe_status.get('branch'))}",
        f"当前任务：{text(vibe_status.get('current_task'))}",
        f"下一步：{text(vibe_status.get('next_action'))}",
        f"参与者：{', '.join(participants) if participants else '未指定'}",
        f"阻塞项：{', '.join(blockers) if blockers else '无'}",
        f"更新时间：{text(vibe_status.get('updated_at'), '未知')}",
        f"心跳：{heartbeat}",
        "",
        "最近事件：",
    ]

    if events:
        lines.extend(
            f"- {text(event.get('time'), '未知')} {text(event.get('text'), '')}"
            for event in events[-MAX_EVENT_ITEMS:]
            if isinstance(event, dict)
        )
    else:
        lines.append("- 暂无")

    lines.extend([
        "",
        "Codex 用量：",
        f"- 5 小时额度剩余：{percent(usage.five_hour_percent_left)}，重置：{text(usage.five_hour_reset, '未知')}",
        f"- 周额度剩余：{percent(usage.weekly_percent_left)}，重置：{text(usage.weekly_reset, '未知')}",
        f"- 本机 Token 消耗近 24 小时：{token_count(token_24h.get('total_tokens'))}，缓存命中：{cache_hit(token_24h.get('cache_hit_percent'))}",
        f"- 本机 Token 消耗近 7 天：{token_count(token_7d.get('total_tokens'))}，缓存命中：{cache_hit(token_7d.get('cache_hit_percent'))}",
        "- Token 数来自本机 Codex 会话文件；额度百分比来自服务器侧 RPC。",
        f"- 数据来源：{text(usage.source, '未知')}",
        f"- 用量更新时间：{text(usage.last_updated, '未知')}",
    ])

    if usage.error:
        lines.extend(["", f"提示：{usage.error}"])

    return "\n".join(lines) + "\n"


def generate_presets_text(presets: list) -> str:
    """Generate a plain-text preset list for old Kindle browsers and scripts."""
    lines = [
        "InkDash Presets",
        "=" * 20,
    ]

    for preset in presets:
        lines.extend([
            f"- {preset.get('name', '')}",
            f"  状态：{preset.get('state', '未指定')}",
            f"  当前任务：{preset.get('current_task', '未指定')}",
            f"  下一步：{preset.get('next_action', '未指定')}",
        ])

    if not presets:
        lines.append("- 暂无可用 preset")

    return "\n".join(lines) + "\n"


def build_health_status(usage: CodexUsage, vibe_status: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact health payload for agents and monitoring scripts."""
    status_board = {
        "state": vibe_status.get("state", ""),
        "updated_at": vibe_status.get("updated_at", ""),
        "stale": is_vibe_status_stale(vibe_status),
        "stale_after_seconds": status_stale_after_seconds(),
    }
    return {
        "status": "ok",
        "checked_at": now_display(),
        "status_board": status_board,
        "vibe": status_board,
        "codex": {
            "source": usage.source,
            "last_updated": usage.last_updated,
            "error": usage.error,
        }
    }


def generate_settings_html(message: str = "", message_type: str = "") -> str:
    """Generate settings page HTML."""
    msg_html = ""
    if message:
        msg_class = "success" if message_type == "success" else "error"
        msg_html = f'<div class="{msg_class}">{escape(message)}</div>'
    
    # Server settings
    server_port = server_port_number()
    server_host = server_host_value()
    
    # Refresh settings
    refresh_interval = refresh_interval_seconds()
    refresh_page = page_refresh_seconds()

    # Status board settings
    stale_after_seconds = status_stale_after_seconds()
    
    # Codex settings
    codex_enabled = codex_enabled_flag()
    codex_source = config.get("codex", {}).get("source", "auto")
    session_limit = config.get("codex", {}).get("session_file_limit", 10)
    
    # Display settings
    display = config.get("display", {})
    show_credits = display_flag(display, "show_credits")
    show_plan = display_flag(display, "show_plan_type")
    show_source = display_flag(display, "show_data_source")
    show_updated = display_flag(display, "show_last_updated")
    show_status = display_status_board_enabled(display)
    layout_mode = normalize_layout_mode(display.get("layout_mode", "auto"))
    text_scale_percent = normalize_text_scale(display.get("text_scale_percent", TEXT_SCALE_DEFAULT))
    text_scale_ratio = text_scale_percent / 100.0
    
    def scaled(px: int) -> str:
        return f"{round(px * text_scale_ratio)}px"
    
    def checked(val):
        return "checked" if val else ""
    
    def selected(val, target):
        return "selected" if val == target else ""
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>设置 - InkDash</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: {scaled(16)};
            background: #ffffff;
            color: #000000;
            padding: 20px;
            max-width: 1040px;
            margin: 0 auto;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 2px solid #000000;
            padding-bottom: 15px;
            position: relative;
        }}
        
        .header h1 {{
            font-size: {scaled(32)};
            font-weight: bold;
        }}
        
        .back-btn {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: #000000;
            color: #ffffff;
            border: none;
            padding: 10px 15px;
            font-size: {scaled(16)};
            cursor: pointer;
            border-radius: 4px;
            text-decoration: none;
        }}
        
        .back-btn:hover {{
            background: #333333;
        }}
        
        .settings-section {{
            border: 2px solid #000000;
            border-radius: 4px;
            padding: 20px;
            margin-bottom: 20px;
            background: #f8f8f8;
        }}
        
        .settings-section h2 {{
            font-size: {scaled(22)};
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ccc;
        }}
        
        .form-group {{
            margin-bottom: 15px;
        }}
        
        .form-group label {{
            display: block;
            font-weight: bold;
            margin-bottom: 5px;
            font-size: {scaled(18)};
        }}
        
        .form-group input[type="number"],
        .form-group input[type="text"],
        .form-group select {{
            width: 100%;
            padding: 10px;
            font-size: {scaled(18)};
            border: 1px solid #ddd;
            border-radius: 4px;
            background: #ffffff;
        }}
        
        .form-group .checkbox-label {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: normal;
            cursor: pointer;
            font-size: {scaled(18)};
        }}
        
        .form-group input[type="checkbox"] {{
            width: 24px;
            height: 24px;
            cursor: pointer;
        }}
        
        .form-actions {{
            text-align: center;
            margin-top: 20px;
        }}
        
        .btn {{
            background: #000000;
            color: #ffffff;
            border: none;
            padding: 12px 30px;
            font-size: {scaled(18)};
            cursor: pointer;
            border-radius: 4px;
            margin: 0 10px;
        }}
        
        .btn:hover {{
            background: #333333;
        }}
        
        .btn-secondary {{
            background: #666666;
        }}
        
        .btn-secondary:hover {{
            background: #888888;
        }}
        
        .success {{
            color: #006600;
            background: #e6ffe6;
            border: 1px solid #00cc00;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 15px;
            text-align: center;
        }}
        
        .error {{
            color: #cc0000;
            background: #fff0f0;
            border: 1px solid #ffcccc;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 15px;
            text-align: center;
        }}
        
        .help-text {{
            font-size: {scaled(14)};
            color: #666;
            margin-top: 5px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <a href="/" class="back-btn">返回</a>
        <h1>设置</h1>
    </div>
    
    {msg_html}
    
    <form method="POST" action="/settings">
        <div class="settings-section">
            <h2>服务器设置</h2>
            
            <div class="form-group">
                <label for="port">端口：</label>
                <input type="number" id="port" name="port" value="{server_port}" min="1" max="65535">
                <div class="help-text">服务监听端口，修改后需要重启。</div>
            </div>
            
            <div class="form-group">
                <label for="host">监听地址：</label>
                <input type="text" id="host" name="host" value="{escape(server_host)}">
                <div class="help-text">使用 0.0.0.0 可让同一局域网内的 Kindle 访问。</div>
            </div>
        </div>
        
        <div class="settings-section">
            <h2>刷新设置</h2>
            
            <div class="form-group">
                <label for="refresh_interval">数据刷新间隔（秒）：</label>
                <input type="number" id="refresh_interval" name="refresh_interval" value="{refresh_interval}" min="30" max="3600">
                <div class="help-text">后台读取 Codex 数据的间隔，范围 30-3600 秒。</div>
            </div>
            
            <div class="form-group">
                <label for="refresh_page">页面自动刷新（秒）：</label>
                <input type="number" id="refresh_page" name="refresh_page" value="{refresh_page}" min="30" max="3600">
                <div class="help-text">Kindle 浏览器自动重新加载页面的间隔。</div>
            </div>
        </div>
        
        <div class="settings-section">
            <h2>Codex 设置</h2>
            
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="codex_enabled" {"checked" if codex_enabled else ""}>
                    启用 Codex 用量监控
                </label>
            </div>
            
            <div class="form-group">
                <label for="codex_source">数据来源：</label>
                <select id="codex_source" name="codex_source">
                    <option value="auto" {selected(codex_source, "auto")}>自动（先 CLI，再会话文件）</option>
                    <option value="cli" {selected(codex_source, "cli")}>仅 CLI RPC</option>
                    <option value="session" {selected(codex_source, "session")}>仅会话文件</option>
                </select>
                <div class="help-text">Codex 用量数据的读取方式。</div>
            </div>
            
            <div class="form-group">
                <label for="session_limit">会话文件扫描数量：</label>
                <input type="number" id="session_limit" name="session_limit" value="{session_limit}" min="1" max="100">
                <div class="help-text">最多扫描多少个最近的 Codex 会话文件。</div>
            </div>
        </div>

        <div class="settings-section">
            <h2>状态看板设置</h2>
            
            <div class="form-group">
                <label for="stale_after_seconds">状态过期阈值（秒）：</label>
                <input type="number" id="stale_after_seconds" name="stale_after_seconds" value="{stale_after_seconds}" min="60" max="86400">
                <div class="help-text">超过这个时间没有状态更新时，看板会提示“可能过期”。</div>
            </div>
        </div>
        
        <div class="settings-section">
            <h2>显示设置</h2>

            <div class="form-group">
                <label for="layout_mode">布局模式：</label>
                <select id="layout_mode" name="layout_mode">
                    <option value="auto" {selected(layout_mode, "auto")}>自动适配</option>
                    <option value="portrait" {selected(layout_mode, "portrait")}>强制竖屏布局</option>
                    <option value="landscape" {selected(layout_mode, "landscape")}>强制横屏布局</option>
                </select>
                <div class="help-text">自动模式按屏幕尺寸和方向适配；横屏模式会使用宽屏双栏布局，适合不能自动旋转的设备从网页端手动切换。</div>
            </div>

            <div class="form-group">
                <label for="text_scale_percent">默认字号比例（%）：</label>
                <input type="number" id="text_scale_percent" name="text_scale_percent" value="{text_scale_percent}" min="{TEXT_SCALE_MIN}" max="{TEXT_SCALE_MAX}" step="5">
                <div class="help-text">设置独立于主页面 URL 偏好（?text_scale=200），不影响其他终端。</div>
            </div>
            
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="show_status_board" {"checked" if show_status else ""}>
                    显示状态看板
                </label>
            </div>
            
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="show_plan_type" {"checked" if show_plan else ""}>
                    显示套餐类型
                </label>
            </div>
            
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="show_credits" {"checked" if show_credits else ""}>
                    显示余额
                </label>
            </div>
            
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="show_data_source" {"checked" if show_source else ""}>
                    显示数据来源
                </label>
            </div>
            
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="show_last_updated" {"checked" if show_updated else ""}>
                    显示更新时间
                </label>
            </div>
        </div>
        
        <div class="form-actions">
            <button type="submit" class="btn">保存设置</button>
            <a href="/" class="btn btn-secondary">取消</a>
        </div>
    </form>
</body>
</html>'''
    
    return html


# ============================================================================
# HTTP Request Handler
# ============================================================================

class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler."""

    def send_no_cache_headers(self):
        """Send headers that keep Kindle browsers from showing stale state."""
        self.send_header("Cache-Control", "no-store, no-cache, max-age=0, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def send_json(self, status_code: int, payload: Dict[str, Any]):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_no_cache_headers()
        self.end_headers()
        self.wfile.write(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))

    def is_api_write_authorized(self, parsed_path) -> bool:
        expected = configured_api_token()
        if not expected:
            return True

        supplied = self.headers.get("X-InkDash-Token", "").strip()
        if not supplied:
            supplied = self.headers.get("X-KindleVibe-Token", "").strip()
        if tokens_match(expected, supplied):
            return True

        query_token = parse_qs(parsed_path.query).get("token", [""])[0].strip()
        return tokens_match(expected, query_token)

    def preference_cookies(self) -> SimpleCookie:
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return SimpleCookie()
        return cookies

    def display_preferences(self, parsed_path=None) -> Dict[str, Any]:
        cookies = self.preference_cookies()
        layout_mode = current_layout_mode()
        text_scale_percent = current_text_scale()

        if LAYOUT_COOKIE in cookies:
            layout_mode = normalize_layout_mode(cookies[LAYOUT_COOKIE].value)
        if TEXT_SCALE_COOKIE in cookies:
            text_scale_percent = normalize_text_scale(cookies[TEXT_SCALE_COOKIE].value)

        if parsed_path is not None:
            query = parse_qs(parsed_path.query)
            if "layout" in query:
                layout_mode = normalize_layout_mode(query["layout"][0])
            if "text_scale" in query:
                text_scale_percent = normalize_text_scale(query["text_scale"][0])
            elif "scale" in query:
                text_scale_percent = normalize_text_scale(query["scale"][0])

        return {
            "layout_mode": layout_mode,
            "text_scale_percent": text_scale_percent,
        }

    def send_preference_cookie(self, name: str, value: str):
        self.send_header(
            "Set-Cookie",
            f"{name}={value}; Path=/; Max-Age={PREFERENCE_COOKIE_MAX_AGE}; SameSite=Lax"
        )
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == "/" or path == "/index.html":
            with cache_lock:
                usage = usage_cache

            preferences = self.display_preferences(parsed_path)
            html = generate_main_html(
                usage,
                load_vibe_status(),
                layout_mode=preferences["layout_mode"],
                text_scale_percent=preferences["text_scale_percent"],
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        
        elif path == "/settings":
            html = generate_settings_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif path == "/layout":
            requested = parse_qs(parsed_path.query).get("mode", ["auto"])[0]
            layout_mode = normalize_layout_mode(requested)
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_preference_cookie(LAYOUT_COOKIE, layout_mode)
            self.send_no_cache_headers()
            self.end_headers()

        elif path == "/text-scale":
            requested = parse_qs(parsed_path.query).get("scale", [TEXT_SCALE_DEFAULT])[0]
            text_scale_percent = normalize_text_scale(requested)
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_preference_cookie(TEXT_SCALE_COOKIE, str(text_scale_percent))
            self.send_no_cache_headers()
            self.end_headers()

        elif path == "/status.txt":
            with cache_lock:
                usage = usage_cache

            preferences = self.display_preferences(parsed_path)
            status_text = generate_status_text(
                usage,
                load_vibe_status(),
                layout_mode=preferences["layout_mode"],
                text_scale_percent=preferences["text_scale_percent"],
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(status_text.encode("utf-8"))

        elif path == "/presets.txt":
            presets_text = generate_presets_text(load_vibe_presets())
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(presets_text.encode("utf-8"))
        
        elif path == "/api/usage":
            with cache_lock:
                usage = usage_cache
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(json.dumps(usage.to_dict(), indent=2, ensure_ascii=False).encode("utf-8"))

        elif path == "/api/health":
            with cache_lock:
                usage = usage_cache

            health = build_health_status(usage, load_vibe_status())
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(json.dumps(health, indent=2, ensure_ascii=False).encode("utf-8"))

        elif path in ("/api/vibe", "/api/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(json.dumps(load_vibe_status(), indent=2, ensure_ascii=False).encode("utf-8"))

        elif path == "/api/presets":
            self.send_json(200, {"presets": load_vibe_presets()})
        
        elif path == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(json.dumps(public_config(), indent=2, ensure_ascii=False).encode("utf-8"))
        
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>404 Not Found</h1>")
    
    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/settings":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            params = parse_qs(post_data)
            
            try:
                # Update server settings
                if "port" in params:
                    config["server"]["port"] = int(params["port"][0])
                if "host" in params:
                    config["server"]["host"] = params["host"][0]
                
                # Update refresh settings
                if "refresh_interval" in params:
                    interval = int(params["refresh_interval"][0])
                    config["refresh"]["interval_seconds"] = max(30, min(3600, interval))
                if "refresh_page" in params:
                    page_refresh = int(params["refresh_page"][0])
                    config["refresh"]["auto_refresh_page_ms"] = max(30, min(3600, page_refresh)) * 1000
                
                # Update codex settings
                config["codex"]["enabled"] = "codex_enabled" in params
                if "codex_source" in params:
                    config["codex"]["source"] = params["codex_source"][0]
                if "session_limit" in params:
                    limit = int(params["session_limit"][0])
                    config["codex"]["session_file_limit"] = max(1, min(100, limit))

                # Update status board settings
                config.setdefault("status", {})
                if "stale_after_seconds" in params:
                    stale_after = int(params["stale_after_seconds"][0])
                    config["status"]["stale_after_seconds"] = max(60, min(86400, stale_after))
                    config.pop("vibe", None)
                
                # Update display settings
                config["display"]["show_plan_type"] = "show_plan_type" in params
                config["display"]["show_credits"] = "show_credits" in params
                config["display"]["show_data_source"] = "show_data_source" in params
                config["display"]["show_last_updated"] = "show_last_updated" in params
                show_status_board = "show_status_board" in params or "show_vibe_board" in params
                config["display"]["show_status_board"] = show_status_board
                config["display"].pop("show_vibe_board", None)
                if "layout_mode" in params:
                    config["display"]["layout_mode"] = normalize_layout_mode(params["layout_mode"][0])
                if "text_scale_percent" in params:
                    config["display"]["text_scale_percent"] = normalize_text_scale(params["text_scale_percent"][0])
                
                # Save config
                if save_config(config):
                    logger.info("Settings saved successfully")
                    html = generate_settings_html("设置已保存。", "success")
                else:
                    html = generate_settings_html("保存设置失败。", "error")
                
            except Exception as e:
                logger.exception("Error saving settings")
                html = generate_settings_html(f"错误：{str(e)}", "error")
            
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_no_cache_headers()
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif path in ("/api/vibe", "/api/status"):
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            if not self.is_api_write_authorized(parsed_path):
                self.send_json(401, {"error": "未授权：缺少或错误的 API token"})
                return

            try:
                payload = json.loads(raw_body or "{}")
                status = update_vibe_status(payload)
                self.send_json(200, status)
            except (json.JSONDecodeError, ValueError) as e:
                self.send_json(400, {"error": f"请求格式错误：{str(e)}"})
            except Exception as e:
                logger.exception("Error updating vibe status")
                self.send_json(500, {"error": f"保存状态失败：{str(e)}"})
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        request_line = args[0] if args else ""
        logger.debug("HTTP %s", redact_sensitive_request_line(str(request_line)))


# ============================================================================
# Main Entry Point
# ============================================================================

def parse_args(argv=None):
    """Parse command-line overrides for local development."""
    parser = argparse.ArgumentParser(
        description="Kindle 友好的 Codex 用量常亮状态面板"
    )
    parser.add_argument("--port", type=int, help="覆盖 config.json 中的服务端口")
    parser.add_argument("--host", help="覆盖 config.json 中的监听地址")
    return parser.parse_args(argv)


def get_local_ip() -> str:
    """Get the local IP address of this machine (excluding VPN)."""
    import socket
    import subprocess
    
    # VPN interfaces to skip
    vpn_prefixes = ('utun', 'tun', 'tap', 'ppp', 'ipsec', 'wg')
    
    try:
        # Method 1: Try to get IP from network interfaces using ifconfig
        result = subprocess.run(
            ['ifconfig'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            current_interface = None
            for line in result.stdout.split('\n'):
                # Detect interface name
                if not line.startswith(' ') and ':' in line:
                    current_interface = line.split(':')[0].strip()
                
                # Look for inet address
                if 'inet ' in line and current_interface:
                    # Skip VPN interfaces
                    if current_interface.startswith(vpn_prefixes):
                        continue
                    
                    # Skip loopback
                    if '127.0.0.1' in line:
                        continue
                    
                    # Extract IP
                    parts = line.strip().split()
                    for i, part in enumerate(parts):
                        if part == 'inet' and i + 1 < len(parts):
                            ip = parts[i + 1]
                            # Verify it's a valid local IP
                            if ip.startswith(('192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.20.', '172.21.', '172.22.', '172.23.', '172.24.', '172.25.', '172.26.', '172.27.', '172.28.', '172.29.', '172.30.', '172.31.')):
                                return ip
        
        # Method 2: Fallback to socket method
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'


def main():
    """Main entry point."""
    global config
    
    # Reload config in case it was modified
    config = load_config()
    args = parse_args()
    if args.port:
        config.setdefault("server", {})["port"] = args.port
    if args.host:
        config.setdefault("server", {})["host"] = args.host
    
    server_port = server_port_number()
    server_host = server_host_value()
    
    # Get local IP
    local_ip = get_local_ip()
    
    # Start background refresh thread
    refresh_thread = threading.Thread(target=refresh_cache, daemon=True)
    refresh_thread.start()
    logger.info("Background refresh thread started")
    
    # Initial fetch
    logger.info("Fetching initial Codex usage data...")
    global usage_cache
    usage_cache = fetch_codex_usage()
    logger.info(f"Initial fetch complete: 5h={usage_cache.five_hour_percent_left}%, weekly={usage_cache.weekly_percent_left}%")
    
    # Start HTTP server
    server = HTTPServer((server_host, server_port), RequestHandler)
    
    # Print connection info
    print("\n" + "=" * 50)
    print("  InkDash 已启动")
    print("=" * 50)
    print(f"\n  本机访问:  http://localhost:{server_port}")
    print(f"  局域网访问: http://{local_ip}:{server_port}")
    print(f"\n  请在 Kindle 浏览器中打开局域网地址")
    print("=" * 50 + "\n")
    
    logger.info(f"Starting InkDash on http://{local_ip}:{server_port}")
    logger.info("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
