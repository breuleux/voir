import os

from .common import NotAvailable

IMPORT_ERROR = None
try:
    import pyhlml
except ImportError as err:
    IMPORT_ERROR = err


def is_installed():
    return IMPORT_ERROR is None

#
# pyhlml use the same enum as nvidia
#
NVML_ERROR_NOT_SUPPORTED = 3
NVML_TEMPERATURE_GPU     = 0

NVSMI_UUID = 6
NVSMI_INDEX = 17
NVSMI_NAME = 4
NVSMI_MEMORY_TOTAL = 50
NVSMI_MEMORY_FREE = 51
NVSMI_MEMORY_USED = 52
NVSMI_TEMPERATURE_GPU = 130
NVSMI_UTILIZATION_GPU = 60
NVSMI_UTILIZATION_MEM = 61
NVSMI_POWER_DRAW = 141


def fix_num(n):
    if n == "N/A":
        n = -1
    return n


def tostr(data):
    if (isinstance(data, bytes)):
        return data.decode("utf-8")
    return str(data)


def handle_error(err):
    if (err.value == NVML_ERROR_NOT_SUPPORTED):
        return "N/A"
    else:
        return err.__str__()


def safecall(call, *args):
    try:
        return call(*args)
    except pyhlml.HLMLError as err:
        return handle_error(err)


def make_gpu_info(handles, selection):
    gpu_infos = {}

    for gid, handle in handles.items():
        uuid = tostr(safecall(pyhlml.hlmlDeviceGetUUID, handle))

        is_selected = (selection is None) or (selection and (str(gid) in selection or uuid in selection))
        if not is_selected:
            continue

        memInfo = pyhlml.hlmlDeviceGetMemoryInfo(handle)
        util = pyhlml.hlmlDeviceGetUtilizationRates(handle)

        gpu_infos[gid] = {
            'minor_number': tostr(safecall(pyhlml.hlmlDeviceGetMinorNumber, handle)),
            "device": gid,
            "product": tostr(safecall(pyhlml.hlmlDeviceGetName, handle)),
            "memory": {
                "used": memInfo.used / 1024 / 1024,
                "total": memInfo.total / 1024 / 1024,
            },
            "utilization": {
                "compute": util,
                "memory": memInfo.used / memInfo.total,
            },
            "temperature": fix_num(safecall(pyhlml.hlmlDeviceGetTemperature, handle, NVML_TEMPERATURE_GPU)),
            "power": fix_num(safecall(pyhlml.hlmlDeviceGetPowerUsage, handle)) / 1000.0,
            "selection_variable": "HABANA_VISIBLE_MODULES",
        }

    return gpu_infos

class DeviceSMI:
    def _setup(self):
        self.handles = {}

        if IMPORT_ERROR is not None:
            raise IMPORT_ERROR
        try:
            pyhlml.hlmlInit()
        except pyhlml.hlml_error.HLMLError_AlreadyInitialized as err:
            pass
        except pyhlml.hlml_error as err:
            raise NotAvailable() from err

        deviceCount = pyhlml.hlmlDeviceGetCount()

        for i in range(0, deviceCount):
            self.handles[i] = pyhlml.hlmlDeviceGetHandleByIndex(i)

    def __init__(self) -> None:
        self.hlsmi = None
        self._setup()

    @property
    def arch(self):
        return "hpu"

    @property
    def visible_devices(self):
        return os.environ.get("HABANA_VISIBLE_MODULES", None)

    def get_gpus_info(self, selection=None):
        return make_gpu_info(self.handles, selection)

    def close(self):
        pass
