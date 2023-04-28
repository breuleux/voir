import os

IMPORT_ERROR = None
try:
    from pynvml import nvmlInit
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


def is_available():
    return IMPORT_ERROR is None


def get_arch():
    return "cuda"


def get_visible_devices():
    return os.environ.get("CUDA_VISIBLE_DEVICES", None)


class DeviceSMI:
    def __init__(self) -> None:
        if IMPORT_ERROR is not None:
            raise IMPORT_ERROR

        nvmlInit()
        self.nvsmi = nvidia_smi.getInstance()

    def get_gpus_info(self):
        to_query = [
            "gpu_name",
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

        return {str(i): parse_gpu(g, i) for i, g in enumerate(gpus)}

    def close(self):
        pass
