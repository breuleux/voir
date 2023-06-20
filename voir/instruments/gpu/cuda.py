import os

from .common import NotAvailable

IMPORT_ERROR = None
try:
    from pynvml import nvmlInit
    from pynvml.nvml import (
        NVMLError_DriverNotLoaded,
        NVMLError_LibraryNotFound,
    )
    from pynvml.smi import nvidia_smi
except ImportError as err:
    IMPORT_ERROR = err


def fix_num(n):
    if n == "N/A":
        n = None
    return n


def parse_gpu(gpu, gid):
    mem = gpu["fb_memory_usage"]
    used = fix_num(mem["used"])
    total = fix_num(mem["total"])
    compute = fix_num(gpu["utilization"]["gpu_util"])
    if compute:
        compute /= 100
    return {
        "device": gid,
        "product": gpu["product_name"],
        "memory": {
            "used": used,
            "total": total,
        },
        "utilization": {
            "compute": compute,
            "memory": total and used and (used / total),
        },
        "temperature": fix_num(gpu["temperature"]["gpu_temp"]),
        "power": fix_num(gpu["power_readings"]["power_draw"]),
        "selection_variable": "CUDA_VISIBLE_DEVICES",
    }


def is_installed():
    return IMPORT_ERROR is None


class DeviceSMI:
    def __init__(self) -> None:
        if IMPORT_ERROR is not None:
            raise IMPORT_ERROR

        try:
            nvmlInit()
            self.nvsmi = nvidia_smi.getInstance()
        except NVMLError_LibraryNotFound as err:
            raise NotAvailable() from err

        except NVMLError_DriverNotLoaded as err:
            raise NotAvailable() from err

    @property
    def arch(self):
        return "cuda"

    @property
    def visible_devices(self):
        return os.environ.get("CUDA_VISIBLE_DEVICES", None)

    def get_gpus_info(self, selection=None):
        to_query = [
            "uuid",  # Globally unique immutable alphanumeric identifier of the GPU
            "index",  # Zero based index of the GPU. Can change at each boot.
            "gpu_name",  # Official Product name
            "memory.free",
            "memory.used",
            "memory.total",
            "temperature.gpu",
            "utilization.gpu",
            "utilization.memory",
            "power.draw",
        ]
        results = self.nvsmi.DeviceQuery(",".join(to_query))

        if not results or "gpu" not in results:
            return {}

        gpus = results["gpu"]
        if not isinstance(gpus, list):
            gpus = [gpus]

        # To support MIG we start using UUID instead of indexes
        # Nevertheless indexes are useful to quickly select specific GPUs
        # so we support selecting GPUs using both
        results = dict()
        for i, g in enumerate(gpus):
            i = str(i)
            uuid = g["uuid"]

            if (selection is None) or (
                selection and (i in selection or uuid in selection)
            ):
                results[uuid] = parse_gpu(g, i)

        return results

    def close(self):
        pass
