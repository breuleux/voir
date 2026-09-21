import os
import shutil
import subprocess

from .common import NotAvailable

IMPORT_ERROR = None
try:
    # pip install dpctl
    import dpctl
except ImportError as err:
    IMPORT_ERROR = err

# Metrics understood by `xpu-smi dump -m`:
# 0. GPU Utilization (%), per tile; device-level averages tiles.
# 1. GPU Power (W)
# 3. GPU Core Temperature (Celsius)
# 5. GPU Memory Utilization (%)
# 18. GPU Memory Used (MiB)
# Utilization and temperature require elevated privileges on some systems
# and show up as "N/A" otherwise; everything degrades to 0.
_XPU_SMI_METRICS = ["0", "1", "3", "5", "18"]


def _parse(val, type, default):
    try:
        return type(val)
    except (ValueError, TypeError):
        return default


def _smi_rows():
    """Best-effort `xpu-smi dump` rows, one per device.

    Returns a list of dicts keyed by metric name, ordered like the
    devices dpctl reports, or an empty list when xpu-smi is missing or
    the output cannot be parsed.
    """
    if shutil.which("xpu-smi") is None:
        return []

    try:
        output = subprocess.check_output(
            [
                "xpu-smi",
                "dump",
                "-d",
                "-1",  # All devices
                "-m",
                ",".join(_XPU_SMI_METRICS),
                "-n",
                "1",  # Run once
            ],
            text=True,
            stderr=subprocess.DEVNULL,  # xpu-smi prints privilege warnings on stderr
            timeout=30,
        )
    except Exception:
        return []

    lines = [line.strip() for line in output.splitlines() if line.strip()]

    if len(lines) < 2:
        return []

    # Header: Timestamp, DeviceId, then one column per requested metric.
    header = [column.strip().lower() for column in lines[0].split(",")]
    if not header[1:2] == ["deviceid"]:
        return []

    rows = []
    for line in lines[1:]:
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != len(header):
            continue

        try:
            device_id = int(fields[1])
        except ValueError:
            continue

        metrics = fields[2:]
        # Pad/truncate defensively if the vendor tool omits a metric.
        get = lambda i: metrics[i] if i < len(metrics) else "N/A"

        rows.append(
            {
                "device": device_id,
                "utilization": _parse(get(0), float, 0) / 100,
                "power": _parse(get(1), float, 0),
                "temperature": _parse(get(2), float, 0),
                "memory_utilization": _parse(get(3), float, 0) / 100,
                "memory_used": _parse(get(4), float, 0),
            }
        )

    return rows


def query_gpu_data(gpus, device_ids=None):
    """Map each visible dpctl GPU to its physical (xpu-smi) device id.

    When a single device is selected via ONEAPI_DEVICE_SELECTOR, dpctl reports
    it at position 0 but xpu-smi still keys its metrics by the physical id, and
    `self.device_ids` holds that physical id. Without this mapping the visible
    device would be looked up under the wrong id (or dropped entirely).
    """
    rows = _smi_rows()
    by_device = {row.pop("device"): row for row in rows}

    if device_ids is None:
        device_ids = list(range(len(gpus)))

    data = []
    for pos, gpu in enumerate(gpus):
        dev_id = device_ids[pos] if pos < len(device_ids) else pos
        row = by_device.get(dev_id, {})
        total_size = gpu.global_mem_size / (1024 * 1024)

        data.append(
            {
                "device": f"level_zero:{dev_id}",
                "product": gpu.name,
                "memory": {
                    "used": row.get("memory_used", 0),
                    "total": total_size,
                },
                "utilization": {
                    "compute": row.get("utilization", 0),
                    "memory": row.get("memory_utilization", 0),
                },
                "temperature": row.get("temperature", 0),
                "power": row.get("power", 0),
                "selection_variable": "ONEAPI_DEVICE_SELECTOR",
            }
        )
    return data


def get_devices():
    return dpctl.get_devices()


def get_gpus():
    gpus = []
    cpus = []

    for device in get_devices():
        # GPUs are shown as level_zero AND openCL
        if device.is_gpu and "level_zero" in device.get_filter_string():
            gpus.append(device)

        if device.is_cpu:
            cpus.append(device)

    return gpus


def is_installed():
    return IMPORT_ERROR is None


class DeviceSMI:
    def __init__(self) -> None:
        if IMPORT_ERROR is not None:
            raise NotAvailable from IMPORT_ERROR

        self.gpus = get_gpus()
        visible_devices = os.environ.get("ONEAPI_DEVICE_SELECTOR", None)

        if visible_devices is None:
            self.device_ids = list(range(len(self.gpus)))
        else:
            device_ids = []
            for device in visible_devices.split(","):
                device_ids.append(int(device.split(":")[-1]))

            self.device_ids = device_ids

    @property
    def arch(self):
        return "xpu"

    @property
    def visible_devices(self):
        return os.environ.get("ONEAPI_DEVICE_SELECTOR", None)

    def get_gpus_info(self, selection=None):
        entries = query_gpu_data(self.gpus, self.device_ids)
        info = {}
        for pos, entry in enumerate(entries):
            dev_id = self.device_ids[pos] if pos < len(self.device_ids) else pos
            info[dev_id] = entry
        return info

    def close(self):
        pass

    def system_info(self):
        info = {}

        # GPU driver version, straight from the SYCL/level-zero runtime.
        for gpu in self.gpus[:1]:
            driver = getattr(gpu, "driver_version", None)
            if driver:
                info["GPU_DRIVER_VERSION"] = driver

        # xpu-smi and Level Zero versions (plain `Key: value` output).
        try:
            if shutil.which("xpu-smi") is not None:
                output = subprocess.check_output(
                    ["xpu-smi", "--version"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
                for line in output.splitlines():
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    if not value:
                        continue
                    if key == "Level Zero Version":
                        info["LEVEL_ZERO_VERSION"] = value
                    elif key == "Version" and "XPU_SMI_VERSION" not in info:
                        info["XPU_SMI_VERSION"] = value
        except Exception:
            pass

        return info
