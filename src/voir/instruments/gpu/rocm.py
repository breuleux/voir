"""AMD GPU backend using the amdsmi python API.

https://rocm.docs.amd.com/projects/amdsmi/en/latest/reference/amdsmi-py-api.html
"""

import os

from .common import NotAvailable

IMPORT_ERROR = None
try:
    try:
        import amdsmi
    except ImportError:
        # amdsmi ships with ROCm but is not always installed in the environment
        import sys

        sys.path.append(
            os.path.join(os.environ.get("ROCM_PATH") or "/opt/rocm", "share/amd_smi")
        )
        import amdsmi

except ImportError as err:
    IMPORT_ERROR = err


def safecall(call, *args, default=-1):
    """Call an amdsmi function, returning ``default`` if the metric is unavailable"""
    try:
        value = call(*args)
    except amdsmi.AmdSmiException:
        return default

    if value == "N/A":
        return default
    return value


def get_gpu_use(handle):
    """Return the current GPU usage as a percentage"""
    activity = safecall(amdsmi.amdsmi_get_gpu_activity, handle, default={})
    value = activity.get("gfx_activity", "N/A")
    return -1 if value == "N/A" else value


def get_mem_info(handle, memType=None):
    """Return the (used, total) memory in bytes"""
    if memType is None:
        memType = amdsmi.AmdSmiMemoryType.VRAM

    used = safecall(amdsmi.amdsmi_get_gpu_memory_usage, handle, memType)
    total = safecall(amdsmi.amdsmi_get_gpu_memory_total, handle, memType)
    return used, total


def get_temp(handle):
    """Return the current temperature in Celsius"""
    # Instinct GPUs do not expose the EDGE sensor, consumer GPUs might not expose JUNCTION
    for sensor in (
        amdsmi.AmdSmiTemperatureType.JUNCTION,
        amdsmi.AmdSmiTemperatureType.HOTSPOT,
        amdsmi.AmdSmiTemperatureType.EDGE,
    ):
        temp = safecall(
            amdsmi.amdsmi_get_temp_metric,
            handle,
            sensor,
            amdsmi.AmdSmiTemperatureMetric.CURRENT,
        )
        if temp != -1:
            return temp
    return -1


def get_power(handle):
    """Return the current power draw in Watts"""
    info = safecall(amdsmi.amdsmi_get_power_info, handle, default={})

    for key in ("current_socket_power", "average_socket_power", "socket_power"):
        value = info.get(key, "N/A")
        if value != "N/A":
            return value
    return -1


def get_product_name(handle):
    info = safecall(amdsmi.amdsmi_get_gpu_asic_info, handle, default={})
    return info.get("market_name", "N/A")


def get_device_index(handle, default):
    """Return the HIP index of the device, which is what ROCR_VISIBLE_DEVICES uses"""
    info = safecall(amdsmi.amdsmi_get_gpu_enumeration_info, handle, default={})
    hip_id = info.get("hip_id", "N/A")
    return default if hip_id == "N/A" else hip_id


def get_device_uuid(handle):
    info = safecall(amdsmi.amdsmi_get_gpu_enumeration_info, handle, default={})
    return info.get("hip_uuid", "N/A")


def is_installed():
    return IMPORT_ERROR is None


class DeviceSMI:
    def __init__(self) -> None:
        if IMPORT_ERROR is not None:
            raise IMPORT_ERROR

        try:
            amdsmi.amdsmi_init(amdsmi.AmdSmiInitFlags.INIT_AMD_GPUS)
        except amdsmi.AmdSmiException as err:
            raise NotAvailable(f"amdsmi failed to initialize: {err}") from err

        self.initialized = True

        handles = amdsmi.amdsmi_get_processor_handles()
        self.handles = {
            get_device_index(handle, i): handle for i, handle in enumerate(handles)
        }
        self.devices = sorted(self.handles.keys())
        self.uuids = {
            device: get_device_uuid(handle) for device, handle in self.handles.items()
        }

    def get_gpu_info(self, device):
        handle = self.handles[device]

        util = get_gpu_use(handle)
        used, total = get_mem_info(handle)
        temp = get_temp(handle)
        power = get_power(handle)

        return {
            "device": device,
            "product": get_product_name(handle),
            "memory": {
                "used": used // (1024**2),
                "total": total // (1024**2),
            },
            "utilization": {
                "compute": float(util) / 100,
                "memory": used / total if total > 0 else -1,
            },
            "temperature": temp,
            "power": power,
            "selection_variable": "ROCR_VISIBLE_DEVICES",
        }

    @property
    def arch(self):
        return "rocm"

    @property
    def visible_devices(self):
        return os.environ.get("ROCR_VISIBLE_DEVICES", None)

    def get_gpus_info(self, selection=None):
        gpus = dict()
        for device in self.devices:
            if (selection is None) or (
                selection
                and (str(device) in selection or self.uuids[device] in selection)
            ):
                gpus[device] = self.get_gpu_info(device)

        return gpus

    def close(self):
        if self.initialized:
            self.initialized = False
            try:
                amdsmi.amdsmi_shut_down()
            except amdsmi.AmdSmiException:
                pass

    def system_info(self):
        info = {}

        if self.devices:
            driver = safecall(
                amdsmi.amdsmi_get_gpu_driver_info,
                self.handles[self.devices[0]],
                default={},
            )
            info["ROCM_KERNEL_DRIVER_VERSION"] = driver.get("driver_version", "N/A")

        try:
            ok, version = amdsmi.amdsmi_get_rocm_version()
            info["ROCM_VERSION"] = version if ok else "N/A"
        except (AttributeError, amdsmi.AmdSmiException):
            pass

        return info
