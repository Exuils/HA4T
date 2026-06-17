# -*- coding: utf-8 -*-
"""
性能采集解析器框架。

每个指标对应一个 Parser 子类，负责两件事：
  1. ``shell_snippet(pid)`` → 生成该指标在 ADB shell 中需要执行的命令片段
  2. ``parse(raw_stdout)``   → 从 ADB shell 原始输出中提取该指标的值

所有 Parser 的 shell_snippet 会被 ``AdbShellBuilder`` 合并为一条 ADB shell 命令，
实现**一次 ADB 往返采集全部指标**。

新增指标流程：
  1. 继承 ``BaseParser``，实现 ``shell_snippet`` 和 ``parse``
  2. 在 ``AndroidMonitor.__init__`` 的 ``parsers`` 列表里注册
"""

import re

# ── 帧标记 ──────────────────────────────────────────────────
# 各 Parser 的输出之间用 @@@NAME@@@ 分隔，parse 时据此定位自己的那一段。
# 避免不同 Parser 的输出互相干扰。

_FRAME = "@@@{name}@@@"

def _frame(name: str) -> str:
    return _FRAME.format(name=name)


class BaseParser:
    """解析器基类。

    子类必须定义：
      name          — 指标名，用于 collect_metrics 过滤
      shell_snippet — 返回命令列表（每元素一行）
      parse         — 从完整 stdout 中返回 {字段: 值}
      fields        — 返回本解析器产生的字段名列表
    """

    name: str = ""

    def shell_snippet(self, pid: str) -> list[str]:
        """返回需追加到 ADB shell 脚本的命令列表（每元素一行）。"""
        return []

    def parse(self, raw_stdout: str) -> dict:
        """从 ``adb shell`` 原始 stdout 中解析本指标数据。"""
        return {}

    def fields(self) -> list[str]:
        """本解析器输出的字段名列表。"""
        return []


# ═══════════════════════════════════════════════════════════════
# /proc/stat — 系统总 CPU + 每核 CPU 原始 tick 计数器
#
# 用法：后端用两次采样的差值算利用率
#   cpu% = (total_delta - idle_delta) / total_delta * 100
# ═══════════════════════════════════════════════════════════════

_CPUSTAT_FIELDS = ['user', 'nice', 'sys', 'idle', 'iowait', 'irq', 'softirq', 'steal']


def _parse_cpu_line(line: str) -> dict | None:
    """解析一行 ``/proc/stat`` 的 cpu/cpuN 行 → ``{user, nice, sys, idle, ...}``。"""
    parts = line.split()
    if not parts or not parts[0].startswith('cpu'):
        return None
    vals = {}
    for i, f in enumerate(_CPUSTAT_FIELDS):
        try:
            vals[f] = int(parts[1 + i]) if (1 + i) < len(parts) else 0
        except (ValueError, IndexError):
            vals[f] = 0
    return vals


class ProcStatParser(BaseParser):
    """解析 ``head -9 /proc/stat``，返回系统总 CPU 和每核 raw ticks。

    Returns:
        cpu_stat: ``{user, nice, sys, idle, ...}`` 系统总体
        cores:    ``{"0": {user, ...}, "1": {...}, ...}`` 每核
    """

    name = "cpu"

    def shell_snippet(self, pid: str) -> list[str]:
        return [
            f"echo '{_frame('CPUSTAT')}'",
            f"grep '^cpu' /proc/stat",
        ]

    def parse(self, raw_stdout: str) -> dict:
        cpu_stat = None
        cores = {}
        in_section = False
        for line in raw_stdout.splitlines():
            if _frame('CPUSTAT') in line:
                in_section = True
                continue
            if line.startswith('@@@'):
                in_section = False
                continue
            if not in_section:
                continue
            v = _parse_cpu_line(line)
            if v is None:
                continue
            name = line.split()[0]
            if name == 'cpu':
                cpu_stat = v
            elif name.startswith('cpu') and name[3:].isdigit():
                cores[name[3:]] = v
        return {"cpu_stat": cpu_stat, "cores": cores}

    def fields(self) -> list[str]:
        return ["cpu_stat", "cores"]


# ═══════════════════════════════════════════════════════════════
# schedstat — 进程累计 CPU 纳秒数（水表读数）
#
# ``/proc/<pid>/schedstat`` 第一字段 = se.sum_exec_runtime（纳秒）。
# 只增不减，后端用两次采样差值算 CPU%。
# ═══════════════════════════════════════════════════════════════

class SchedstatParser(BaseParser):
    """读取进程累计 CPU 时间（纳秒），需 PID。

    Returns:
        cpu_ns: se.sum_exec_runtime 纳秒（int），用于后端算 delta %
    """

    name = "cpu"

    def shell_snippet(self, pid: str) -> list[str]:
        return [
            f"echo '{_frame('SCHED')}'",
            f"cat /proc/{pid}/schedstat 2>/dev/null | awk '{{print $1}}'",
        ]

    def parse(self, raw_stdout: str) -> dict:
        in_section = False
        for line in raw_stdout.splitlines():
            if _frame('SCHED') in line:
                in_section = True
                continue
            if line.startswith('@@@'):
                in_section = False
                continue
            if in_section and line.strip():
                try:
                    return {"cpu_ns": int(line.strip())}
                except ValueError:
                    return {"cpu_ns": None}
        return {"cpu_ns": None}

    def fields(self) -> list[str]:
        return ["cpu_ns"]


# ═══════════════════════════════════════════════════════════════
# VmRSS — 进程物理内存（RSS KB）
#
# RSS = Resident Set Size，进程实际占用的物理内存（含共享库全部计入）。
# 比 dumpsys meminfo PSS 高 10-30%，但读取速度高 10-50 倍。
# ═══════════════════════════════════════════════════════════════

class MemoryParser(BaseParser):
    """读取进程内存，支持 RSS（默认）和 PSS 两种模式。

    RSS 模式：读 ``/proc/<pid>/status:VmRSS``，快，但偏高（共享库重复计入）。
    PSS 模式：读 ``dumpsys meminfo | grep TOTAL PSS``，准确，但慢 ~180ms。

    :param mode: "rss" 或 "pss"

    Returns:
        mem_rss_kb（RSS 模式）或 mem_pss_kb（PSS 模式）
    """

    MODES = {"rss", "pss"}

    def __init__(self, mode: str = "rss"):
        if mode not in self.MODES:
            raise ValueError(f"MemoryParser mode must be one of {self.MODES}, got {mode!r}")
        self.mode = mode

    @property
    def name(self) -> str:
        return "mem"

    def shell_snippet(self, pid: str) -> list[str]:
        if not pid or pid == "''":
            return [
                f"echo '{_frame('MEM')}'",
                r"awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print t-a}' /proc/meminfo",
            ]
        if self.mode == "rss":
            return [
                f"echo '{_frame('MEM')}'",
                f"grep VmRSS /proc/{pid}/status 2>/dev/null | awk '{{print $2}}'",
            ]
        else:
            return [
                f"echo '{_frame('MEM')}'",
                f"dumpsys meminfo {pid} 2>/dev/null | grep 'TOTAL PSS:' | awk '{{print $3}}'",
            ]

    def parse(self, raw_stdout: str) -> dict:
        key = "mem_pss_kb" if self.mode == "pss" else "mem_rss_kb"
        in_section = False
        for line in raw_stdout.splitlines():
            if _frame('MEM') in line:
                in_section = True
                continue
            if line.startswith('@@@'):
                in_section = False
                continue
            if in_section and line.strip():
                try:
                    return {key: int(line.strip())}
                except ValueError:
                    return {key: None}
        return {key: None}

    def fields(self) -> list[str]:
        return ["mem_pss_kb" if self.mode == "pss" else "mem_rss_kb"]


# ═══════════════════════════════════════════════════════════════
# 电池电量 / 温度 — sysfs
# ═══════════════════════════════════════════════════════════════

class BatteryParser(BaseParser):
    """读取电池容量（%）和温度（°C），通过 sysfs，不依赖 PID。

    Returns:
        battery_level: 0-100
        battery_temp:  摄氏度（一位小数）
    """

    name = "battery"

    def shell_snippet(self, pid: str) -> list[str]:
        return [
            f"echo '{_frame('BATT')}'",
            r"cat /sys/class/power_supply/battery/capacity 2>/dev/null || cat /sys/class/power_supply/mmi_battery/capacity 2>/dev/null || echo ''",
            f"echo '{_frame('TEMP')}'",
            r"cat /sys/class/power_supply/battery/temp 2>/dev/null || cat /sys/class/power_supply/mmi_battery/temp 2>/dev/null || echo ''",
        ]

    def parse(self, raw_stdout: str) -> dict:
        result = {"battery_level": None, "battery_temp": None}
        mode = None
        for line in raw_stdout.splitlines():
            if _frame('BATT') in line:
                mode = 'batt'; continue
            if _frame('TEMP') in line:
                mode = 'temp'; continue
            if line.startswith('@@@'):
                mode = None; continue
            if mode == 'batt' and line.strip():
                try:
                    result['battery_level'] = int(line.strip())
                except ValueError:
                    pass
            elif mode == 'temp' and line.strip():
                try:
                    result['battery_temp'] = round(int(line.strip()) / 10.0, 1)
                except ValueError:
                    pass
        return result

    def fields(self) -> list[str]:
        return ["battery_level", "battery_temp"]


# ═══════════════════════════════════════════════════════════════
# ADB Shell 构建器
#
# 将多个 Parser 的 shell_snippet 合并为一条 ADB shell 命令字符串。
# 所有命令在同一 shell 进程中执行，避免多次 ADB 往返。
# ═══════════════════════════════════════════════════════════════

class AdbShellBuilder:
    """将多个 parser 的 shell_snippet 合并为一条 ADB shell 命令。"""

    @staticmethod
    def build(parsers: list[BaseParser], pid: str) -> str:
        lines = []
        for p in parsers:
            lines.extend(p.shell_snippet(pid))
        return '\n'.join(lines)
