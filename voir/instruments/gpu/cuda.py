import os
import traceback

from .common import NotAvailable

IMPORT_ERROR = None
try:
    import pynvml
    from pynvml import NVMLError_DriverNotLoaded, NVMLError_LibraryNotFound
except ImportError as err:
    IMPORT_ERROR = err


def fix_num(n):
    try:
        return float(n)
    except ValueError:
        return -1


def tostr(data):
    if isinstance(data, bytes):
        return data.decode("utf-8")
    return str(data)


def handle_error(err):
    if err.value == pynvml.NVML_ERROR_NOT_SUPPORTED:
        return "N/A"
    else:
        return err.__str__()


def safecall(call, *args):
    try:
        return call(*args)
    except pynvml.NVMLError as err:
        return handle_error(err)


def make_gpu_info(gid, handle, selection):
    uuid = tostr(safecall(pynvml.nvmlDeviceGetUUID, handle))

    is_selected = (selection is None) or (
        selection and (str(gid) in selection or uuid in selection)
    )
    if not is_selected:
        return {}

    memInfo = pynvml.nvmlDeviceGetMemoryInfo(handle)
    util = pynvml.nvmlDeviceGetUtilizationRates(handle)

    return {
        "minor_number": tostr(safecall(pynvml.nvmlDeviceGetMinorNumber, handle)),
        "device": gid,
        "product": tostr(safecall(pynvml.nvmlDeviceGetName, handle)),
        "memory": {
            "used": memInfo.used / 1024 / 1024,
            "total": memInfo.total / 1024 / 1024,
        },
        "utilization": {
            "compute": util.gpu / 100,
            "memory": util.memory,
        },
        "temperature": fix_num(
            safecall(
                pynvml.nvmlDeviceGetTemperature, handle, pynvml.NVML_TEMPERATURE_GPU
            )
        ),
        "power": fix_num(safecall(pynvml.nvmlDeviceGetPowerUsage, handle)) / 1000.0,
        "selection_variable": "CUDA_VISIBLE_DEVICES",
    }


def make_gpu_infos(handles, selection):
    gpu_infos = {}

    for gid, handle in handles.items():
        try:
            if info := make_gpu_info(gid, handle, selection):
                gpu_infos[gid] = info
        except Exception:
            traceback.print_exc()

    return gpu_infos


def is_installed():
    return IMPORT_ERROR is None


class DeviceSMI:
    def _setup(self):
        self.handles = {}

        if IMPORT_ERROR is not None:
            raise IMPORT_ERROR

        try:
            pynvml.nvmlInit()
        except NVMLError_LibraryNotFound as err:
            raise NotAvailable() from err

        except NVMLError_DriverNotLoaded as err:
            raise NotAvailable() from err

        deviceCount = pynvml.nvmlDeviceGetCount()
        for i in range(0, deviceCount):
            self.handles[i] = pynvml.nvmlDeviceGetHandleByIndex(i)

    def __init__(self) -> None:
        self._setup()

    @property
    def arch(self):
        return "cuda"

    @property
    def visible_devices(self):
        return os.environ.get("CUDA_VISIBLE_DEVICES", None)

    def get_gpus_info(self, selection=None):
        return make_gpu_infos(self.handles, selection)

    def system_info(self):
        cuda_driver_version = pynvml.nvmlSystemGetCudaDriverVersion_v2()
        driver_version = pynvml.nvmlSystemGetDriverVersion()
        entries = pynvml.nvmlSystemGetHicVersion()
        nvml_version = pynvml.nvmlSystemGetNVMLVersion()
        return {
            "CUDA_DRIVER": cuda_driver_version,
            "DRIVER_VERSION": driver_version,
            "HIC_VERSION": entries,
            "NVML_VERSION": nvml_version,
        }

    def close(self):
        pass
