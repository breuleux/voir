import os

from .common import NotAvailable

IMPORT_ERROR = None
try:
    import sys

    sys.path.append("/opt/rocm/libexec/rocm_smi/")
    import rsmiBindings as rsmi

except ImportError as err:
    IMPORT_ERROR = err


def rsmi_ret_ok(smi, my_ret, device=None, metric=None, silent=False):
    """Returns true if RSMI call status is 0 (success)

    If status is not 0, error logs are written to the debug log and false is returned

    @param device: DRM device identifier
    @param my_ret: Return of RSMI call (rocm_smi_lib API)
    @param metric: Parameter of GPU currently being analyzed
    """
    if my_ret != rsmi.rsmi_status_t.RSMI_STATUS_SUCCESS:
        err_str = rsmi.c_char_p()
        smi.rsmi_status_string(my_ret, rsmi.byref(err_str))

        returnString = ""
        if device is not None:
            returnString += "%s GPU[%s]:" % (my_ret, device)
        if metric is not None:
            returnString += " %s: " % (metric)
        returnString += "%s\t" % (err_str.value.decode())

        # warnings.warn(returnString, RuntimeWarning)
        return False
    return True


def is_driver_initialized():
    """Returns true if amdgpu is found in the list of initialized modules"""
    import subprocess

    driverInitialized = ""
    try:
        driverInitialized = str(
            subprocess.check_output(
                "cat /sys/module/amdgpu/initstate |grep live", shell=True
            )
        )
    except subprocess.CalledProcessError:
        pass
    if len(driverInitialized) > 0:
        return True
    return False


def initialize_rsmi():
    """initializes rocmsmi if the amdgpu driver is initialized"""
    # Check if amdgpu is initialized before initializing rsmi
    if is_driver_initialized() is True:
        if hasattr(rsmi, "rocmsmi"):
            # ROCm < 6.0
            smi = rsmi.rocmsmi
        else:
            # ROCm >= 6.0
            smi = rsmi.initRsmiBindings()
        ret_init = smi.rsmi_init(0)
        if ret_init != 0:
            raise NotAvailable(
                "ROCm SMI returned %s (the expected value is 0)", ret_init
            )
        return smi
    else:
        raise NotAvailable("Driver not initialized (amdgpu not found in modules)")


def list_devices(smi):
    """Returns a list of GPU devices"""

    numberOfDevices = rsmi.c_uint32(0)
    ret = smi.rsmi_num_monitor_devices(rsmi.byref(numberOfDevices))

    if rsmi_ret_ok(smi, ret):
        deviceList = list(range(numberOfDevices.value))
        return deviceList
    else:
        exit(ret)


def get_gpu_use(smi, device):
    """Return the current GPU usage as a percentage"""
    percent = rsmi.c_uint32()

    ret = smi.rsmi_dev_busy_percent_get(device, rsmi.byref(percent))

    if rsmi_ret_ok(smi, ret, device, "GPU Utilization "):
        return percent.value

    return -1


def get_mem_info(smi, device, memType="vram"):
    """Return the specified memory usage for the specified device

    @param device: DRM device identifier
    @param type: [vram|vis_vram|gtt] Memory type to return
    """
    memType = memType.upper()
    if memType not in rsmi.memory_type_l:
        raise RuntimeError("Invalid memory type %s" % (memType))

    memoryUse = rsmi.c_uint64()
    memoryTot = rsmi.c_uint64()
    memUsed = None
    memTotal = None

    ret = smi.rsmi_dev_memory_usage_get(
        device, rsmi.memory_type_l.index(memType), rsmi.byref(memoryUse)
    )
    if rsmi_ret_ok(smi, ret, device, memType):
        memUsed = memoryUse.value

    ret = smi.rsmi_dev_memory_total_get(
        device, rsmi.memory_type_l.index(memType), rsmi.byref(memoryTot)
    )
    if rsmi_ret_ok(smi, ret, device, memType + " total"):
        memTotal = memoryTot.value
    return (memUsed, memTotal)


def get_temp(smi, device, sensor):
    """Display the current temperature from a given device's sensor

    @param device: DRM device identifier
    @param sensor: Temperature sensor identifier
    """
    temp = rsmi.c_int64(0)
    metric = rsmi.rsmi_temperature_metric_t.RSMI_TEMP_CURRENT
    ret = smi.rsmi_dev_temp_metric_get(
        rsmi.c_uint32(device),
        rsmi.temp_type_lst.index(sensor),
        metric,
        rsmi.byref(temp),
    )
    if rsmi_ret_ok(smi, ret, device, sensor, True):
        return temp.value / 1000
    return -1


def get_power(smi, device):
    """Return the current power level of a given device

    @param device: DRM device identifier
    """
    power = rsmi.c_int64()
    power_type = rsmi.rsmi_power_type_t()

    ret = smi.rsmi_dev_power_get(device, rsmi.byref(power), rsmi.byref(power_type))
    if rsmi_ret_ok(smi, ret, device, "power"):
        return power.value / 1000000
    return -1


def get_product_name(smi, device):
    series = rsmi.create_string_buffer(256)

    smi.rsmi_dev_name_get(device, series, 256)

    series = series.value.decode()

    return series


def is_installed():
    return IMPORT_ERROR is None


class DeviceSMI:
    def __init__(self) -> None:
        if IMPORT_ERROR is not None:
            raise IMPORT_ERROR

        self.smi = initialize_rsmi()
        self.devices = list_devices(self.smi)

    def get_gpu_info(self, device):
        util = get_gpu_use(self.smi, device)
        used, total = get_mem_info(self.smi, device)
        temp = get_temp(self.smi, device, "junction")
        power = get_power(self.smi, device)

        return {
            "device": device,
            "product": get_product_name(self.smi, device),
            "memory": {
                "used": used // (1024**2),
                "total": total // (1024**2),
            },
            "utilization": {
                "compute": float(util) / 100,
                "memory": used / total,
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
            if (selection is None) or (selection and str(device) in selection):
                gpus[device] = self.get_gpu_info(device)

        return gpus

    def close(self):
        pass

    def system_info(self):
        try:
            version_str = rsmi.create_string_buffer(256)
            ret = self.smi.rsmi_version_str_get(
                rsmi.rsmi_sw_component_t.RSMI_SW_COMP_DRIVER, version_str, 256
            )

            if rsmi_ret_ok(self.smi, ret):
                version = version_str.value.decode()
            else:
                version = "N/A"

            return {"ROCM_KERNEL_DRIVER_VERSION": version}
        except Exception:
            import traceback

            traceback.print_exc()
            return {}
