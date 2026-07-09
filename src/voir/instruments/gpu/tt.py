"""Tenstorrent device metrics via Linux sysfs; tt-smi for software version info."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .common import NotAvailable

SNAPSHOT_TIMEOUT = 30
SYSFS_TT_CLASS = Path("/sys/class/tenstorrent")

# Per-ASIC GDDR6 capacity (MiB) from Tenstorrent hardware specs:
# https://docs.tenstorrent.com/aibs/wormhole/index.html#card-comparison-table
# n300 cards expose two ASICs in tt-smi (12 GiB GDDR6 each, 24 GiB per card).
BOARD_GDDR_MIB: dict[str, int] = {
    "n150": 12 * 1024,
    "n300": 12 * 1024,
}

# Optional in-process DRAM usage updates (used MiB, total MiB) keyed by device id.
_runtime_dram_mib: dict[int, tuple[float, float]] = {}


def _read_int(path: Path, default: int = -1) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return default


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return default


def _find_hwmon(pci_device: Path) -> Path | None:
    hwmon_root = pci_device / "hwmon"
    if not hwmon_root.is_dir():
        return None
    for entry in sorted(hwmon_root.iterdir()):
        if not entry.name.startswith("hwmon"):
            continue
        if _read_text(entry / "name") == "wormhole":
            return entry
    return None


def discover_sysfs_devices() -> list[dict]:
    """Return Tenstorrent devices visible under ``/sys/class/tenstorrent``."""
    if not SYSFS_TT_CLASS.is_dir():
        return []

    devices: list[dict] = []
    for link in sorted(SYSFS_TT_CLASS.glob("tenstorrent!*")):
        name = link.name
        if not name.startswith("tenstorrent!"):
            continue
        device_id = int(name.split("!", 1)[1])
        tt_path = link.resolve()
        pci_device = tt_path.parent.parent

        card_type = _read_text(tt_path / "tt_card_type", "Tenstorrent")
        hwmon = _find_hwmon(pci_device)

        telem: dict[str, float | str] = {
            "aiclk": float(_read_int(tt_path / "tt_aiclk")),
            "arcclk": float(_read_int(tt_path / "tt_arcclk")),
            "axiclk": float(_read_int(tt_path / "tt_axiclk")),
            "heartbeat": float(_read_int(tt_path / "tt_heartbeat")),
        }

        power = -1.0
        temperature = -1.0
        current = -1.0
        voltage = -1.0
        if hwmon is not None:
            # Standard hwmon units: temp=m°C, power=µW, curr=mA, in=mV
            temp_raw = _read_int(hwmon / "temp1_input")
            power_raw = _read_int(hwmon / "power1_input")
            curr_raw = _read_int(hwmon / "curr1_input")
            volt_raw = _read_int(hwmon / "in0_input")
            if temp_raw >= 0:
                temperature = temp_raw / 1000.0
            if power_raw >= 0:
                power = power_raw / 1_000_000.0
            if curr_raw >= 0:
                current = curr_raw / 1000.0
            if volt_raw >= 0:
                voltage = volt_raw / 1000.0

        bus_id = pci_device.name if pci_device.name.startswith("0000:") else "N/A"
        devices.append(
            {
                "device_id": device_id,
                "board_info": {
                    "board_type": card_type,
                    "bus_id": bus_id,
                },
                "telemetry": {
                    "power": power,
                    "asic_temperature": temperature,
                    "current": current,
                    "voltage": voltage,
                    **telem,
                },
                "limits": {},
                "firmwares": {
                    "fw_bundle_version": _read_text(tt_path / "tt_fw_bundle_ver"),
                },
                "sysfs_path": str(tt_path),
            }
        )

    return devices


def is_installed() -> bool:
    return bool(discover_sysfs_devices())


def fetch_devices() -> list[dict]:
    """Return device records from sysfs."""
    devices = discover_sysfs_devices()
    return [
        {
            "board_info": entry["board_info"],
            "telemetry": {
                "power": entry["telemetry"].get("power"),
                "asic_temperature": entry["telemetry"].get("asic_temperature"),
                "current": entry["telemetry"].get("current"),
                "voltage": entry["telemetry"].get("voltage"),
                "aiclk": entry["telemetry"].get("aiclk"),
            },
            "limits": entry.get("limits") or {},
            "_device_id": entry["device_id"],
            "_source": "sysfs",
        }
        for entry in devices
    ]


def report_dram_usage(device_id: int, used_mib: float, total_mib: float | None = None) -> None:
    """Publish DRAM usage from the active TT-Metal / TTNN workload."""
    total = total_mib if total_mib is not None else board_gddr_mib("")
    _runtime_dram_mib[device_id] = (used_mib, total)


def clear_dram_usage(device_id: int | None = None) -> None:
    if device_id is None:
        _runtime_dram_mib.clear()
    else:
        _runtime_dram_mib.pop(device_id, None)


def board_gddr_mib(board_type: str) -> float:
    name = (board_type or "").lower()
    for prefix, mib in BOARD_GDDR_MIB.items():
        if prefix in name:
            return float(mib)
    return -1


def _tt_smi_path() -> str | None:
    override = os.environ.get("TT_SMI_PATH")
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        return override
    return shutil.which("tt-smi")


def _parse_float(value: Any, default: float = -1) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return default


def _extract_snapshot_json(stdout: str) -> dict:
    text = stdout.strip()
    if not text:
        raise NotAvailable("tt-smi snapshot was empty")

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise NotAvailable("tt-smi snapshot did not contain JSON")

    return json.loads(text[start : end + 1])


def fetch_snapshot() -> dict | None:
    """Run ``tt-smi -s --snapshot_no_tty`` and return parsed JSON, if available."""
    tt_smi = _tt_smi_path()
    if tt_smi is None:
        return None

    try:
        completed = subprocess.run(
            [tt_smi, "-s", "--snapshot_no_tty"],
            capture_output=True,
            text=True,
            timeout=SNAPSHOT_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None

    if completed.returncode != 0:
        return None

    try:
        return _extract_snapshot_json(completed.stdout)
    except (NotAvailable, json.JSONDecodeError):
        return None


def _sysfs_driver_version() -> str:
    driver = _read_text(Path("/sys/module/tenstorrent/version"))
    if not driver:
        driver = _read_text(Path("/sys/module/tt_kmd/version"))
    return driver


def query_dram_usage_via_ttnn(device_id: int) -> tuple[float, float] | None:
    """Query TT-Metal DRAM allocator stats via ``ttnn.get_memory_view``.

    Disabled by default: opening a device can conflict with TT-XLA workloads.
    Enable with ``VOIR_TT_QUERY_DRAM=1`` for native TT-Metal / TTNN programs.
    """
    if os.environ.get("VOIR_TT_QUERY_DRAM", "0") != "1":
        return None

    try:
        import ttnn
    except ImportError:
        return None

    device = None
    try:
        device = ttnn.open_device(device_id=device_id)
        view = ttnn.get_memory_view(device, ttnn.BufferType.DRAM)
        used = view.num_banks * view.total_bytes_allocated_per_bank
        total = view.num_banks * view.total_bytes_per_bank
        return used / (1024 * 1024), total / (1024 * 1024)
    except Exception:
        return None
    finally:
        if device is not None:
            try:
                ttnn.close_device(device)
            except Exception:
                pass


def _resolve_memory(
    device_id: int,
    board_type: str,
    dram_usage: dict[int, tuple[float, float]] | None,
) -> dict[str, float]:
    used = -1.0
    total = board_gddr_mib(board_type)

    if dram_usage and device_id in dram_usage:
        used, reported_total = dram_usage[device_id]
        if reported_total > 0:
            total = reported_total

    memory_util = used / total if used >= 0 and total > 0 else -1
    return {
        "used": used,
        "total": total,
        "utilization": memory_util,
    }


def make_gpu_info(
    device_id: int,
    device: dict,
    selection: list[str] | None,
    dram_usage: dict[int, tuple[float, float]] | None = None,
):
    if selection is not None and str(device_id) not in selection:
        return {}

    telem = device.get("telemetry") or {}
    board = device.get("board_info") or {}
    limits = device.get("limits") or {}

    power = _parse_float(telem.get("power"))
    tdp = _parse_float(limits.get("tdp_limit"))
    if tdp <= 0 and "n300" in (board.get("board_type") or "").lower():
        tdp = 85.0
    elif tdp <= 0 and "n150" in (board.get("board_type") or "").lower():
        tdp = 80.0
    load = power / tdp if power >= 0 and tdp > 0 else -1

    memory = _resolve_memory(device_id, board.get("board_type", ""), dram_usage)

    info = {
        "device": device_id,
        "product": board.get("board_type") or board.get("board_id") or "Tenstorrent",
        "memory": {"used": memory["used"], "total": memory["total"]},
        "utilization": {
            "compute": load,
            "memory": memory["utilization"],
        },
        "temperature": _parse_float(telem.get("asic_temperature")),
        "power": power,
        "selection_variable": "TT_VISIBLE_DEVICES",
        "aiclk": _parse_float(telem.get("aiclk")),
        "voltage": _parse_float(telem.get("voltage")),
        "current": _parse_float(telem.get("current")),
        "bus_id": board.get("bus_id"),
        "dram_status": board.get("dram_status"),
        "dram_speed": board.get("dram_speed"),
    }
    source = device.get("_source")
    if source:
        info["source"] = source
    return info


def _collect_dram_usage(device_count: int, selection: list[str] | None) -> dict[int, tuple[float, float]]:
    usage: dict[int, tuple[float, float]] = {}

    for device_id in range(device_count):
        if selection is not None and str(device_id) not in selection:
            continue
        if device_id in _runtime_dram_mib:
            usage[device_id] = _runtime_dram_mib[device_id]
            continue
        queried = query_dram_usage_via_ttnn(device_id)
        if queried is not None:
            usage[device_id] = queried

    return usage


def make_gpu_infos(
    devices: list[dict],
    selection: list[str] | None,
    dram_usage: dict[int, tuple[float, float]] | None = None,
):
    if dram_usage is None:
        dram_usage = _collect_dram_usage(len(devices), selection)

    gpus = {}
    for device in devices:
        device_id = device.get("_device_id", len(gpus))
        if info := make_gpu_info(device_id, device, selection, dram_usage):
            gpus[device_id] = info
    return gpus


class DeviceSMI:
    def __init__(self) -> None:
        if not fetch_devices():
            raise NotAvailable("No Tenstorrent devices found (sysfs)")

    @property
    def arch(self) -> str:
        return "tt"

    @property
    def visible_devices(self) -> str | None:
        return os.environ.get("TT_VISIBLE_DEVICES")

    def get_gpus_info(self, selection=None):
        devices = fetch_devices()
        if not devices:
            raise NotAvailable("No Tenstorrent devices found (sysfs)")
        return make_gpu_infos(devices, selection)

    def system_info(self):
        info = {
            "DRIVER": _sysfs_driver_version(),
            "SOURCE": "sysfs",
        }
        snapshot = fetch_snapshot()
        if snapshot is not None:
            host = snapshot.get("host_info") or {}
            sw = snapshot.get("host_sw_vers") or {}
            if host.get("Driver"):
                info["DRIVER"] = host.get("Driver")
            info["TT_SMI"] = sw.get("tt_smi")
            info["TT_UMD"] = sw.get("tt_umd")
            info["PYLUWEN"] = sw.get("pyluwen")
        return info

    def close(self):
        pass
