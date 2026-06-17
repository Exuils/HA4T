# -*- coding: utf-8 -*-
"""
Android 设备性能采集器 — ``AndroidMonitor``。
"""

import subprocess

from .parsers import (
    BaseParser,
    AdbShellBuilder,
    ProcStatParser,
    SchedstatParser,
    MemoryParser,
    BatteryParser,
    _frame,
)


def _adb(serial: str, shell_cmd: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["adb", "-s", serial, "shell", shell_cmd],
            capture_output=True, text=True, encoding='utf-8', timeout=8,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _get_pids(serial: str, package: str) -> list[str]:
    """获取包名前缀匹配的所有 PID（主进程 + :push/:remote 等子进程）。"""
    out = _adb(serial, f"ps -A 2>/dev/null | grep -F '{package}'")
    if not out or not out.stdout:
        return []
    pids = []
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].startswith(package):
            pids.append(parts[1])
    return pids


_FIELD_MAP: dict[str, list[str]] = {
    "cpu":     ["cpu_ns", "cpu_stat", "cores"],
    "mem":     ["mem_rss_kb", "mem_pss_kb"],
    "battery": ["battery_level", "battery_temp"],
}


class AndroidMonitor:
    """Android 设备性能采集器。

    :param serial: ADB 设备序列号
    :param package: 包名（空=全局模式）
    :param track_subprocesses: 是否跟踪子进程，默认 True
    :param memory_mode: "rss"（快速+偏高）或 "pss"（精确+慢 ~180ms），默认 "rss"
    """

    def __init__(self, serial: str, package: str = "",
                 track_subprocesses: bool = True, memory_mode: str = "rss"):
        self.serial = serial
        self.package = package
        self.track_subprocesses = track_subprocesses
        self.memory_mode = memory_mode
        self.pids: list[str] = []

    def refresh_pids(self) -> None:
        if not self.package:
            self.pids = []
            return
        if self.track_subprocesses:
            self.pids = _get_pids(self.serial, self.package)
            return
        # 仅主进程
        out = _adb(self.serial, f"ps -A 2>/dev/null | grep -F '{self.package}'")
        if out and out.stdout:
            for line in out.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[-1] == self.package:
                    self.pids = [parts[1]]
                    return
        self.pids = []

    def _build_shell(self) -> str:
        lines = []
        lines.extend(ProcStatParser().shell_snippet(""))
        if self.pids:
            for pid in self.pids:
                lines.extend(SchedstatParser().shell_snippet(pid))
            lines.extend(MemoryParser(mode=self.memory_mode).shell_snippet(self.pids[0]))
        elif self.package:
            lines.extend(SchedstatParser().shell_snippet("''"))
            lines.extend(MemoryParser(mode=self.memory_mode).shell_snippet("0"))
        else:
            lines.extend(SchedstatParser().shell_snippet("''"))
            lines.extend(MemoryParser(mode=self.memory_mode).shell_snippet("''"))
        lines.extend(BatteryParser().shell_snippet(""))
        return "\n".join(lines)

    def _parse_schedstat(self, raw: str) -> int | None:
        """解析 raw 中所有 SCHED 帧的 cpu_ns 并求和。"""
        total = 0
        found = False
        for line in raw.splitlines():
            if '@@@SCHED@@@' in line:
                found = True
                continue
            if line.startswith('@@@'):
                found = False
                continue
            if found and line.strip():
                try:
                    total += int(line.strip())
                except ValueError:
                    pass
        return total if total > 0 else None

    def collect(self) -> dict:
        if self.package and not self.pids:
            self.refresh_pids()

        shell = self._build_shell()
        proc = _adb(self.serial, shell)
        if proc is None:
            return {}

        raw = proc.stdout
        result = {}
        result.update(ProcStatParser().parse(raw))
        result["cpu_ns"] = self._parse_schedstat(raw)
        result.update(MemoryParser(mode=self.memory_mode).parse(raw))
        result.update(BatteryParser().parse(raw))

        if self.package and result.get("cpu_ns") is None:
            self.refresh_pids()
            if self.pids:
                shell = self._build_shell()
                proc = _adb(self.serial, shell)
                if proc:
                    raw = proc.stdout
                    result = {}
                    result.update(ProcStatParser().parse(raw))
                    result["cpu_ns"] = self._parse_schedstat(raw)
                    result.update(MemoryParser(mode=self.memory_mode).parse(raw))
                    result.update(BatteryParser().parse(raw))

        return result

    def collect_metrics(self, metrics: list[str]) -> dict:
        all_data = self.collect()
        out = {}
        for m in metrics:
            for key in _FIELD_MAP.get(m, [m]):
                if key in all_data:
                    out[key] = all_data[key]
        return out
