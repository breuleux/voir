import os
import subprocess

from .common import NotAvailable

IMPORT_ERROR = None
try:
    # python -m pip install --index-url https://pypi.anaconda.org/intel/simple dpctl
    import dpctl
except ImportError as err:
    IMPORT_ERROR = err


def query_gpu_data(gpu):
    # 0. GPU Utilization (%), GPU active time of the elapsed time, per tile or device. Device-level is the average value of tiles for multi-tiles.
    # 1. GPU Power (W), per tile or device.
    # 2. GPU Frequency (MHz), per tile or device. Device-level is the average value of tiles for multi-tiles.
    # 3. GPU Core Temperature (Celsius Degree), per tile or device. Device-level is the average value of tiles for multi-tiles.
    # 4. GPU Memory Temperature (Celsius Degree), per tile or device. Device-level is the average value of tiles for multi-tiles.
    # 5. GPU Memory Utilization (%), per tile or device. Device-level is the average value of tiles for multi-tiles.
    # 6. GPU Memory Read (kB/s), per tile or device. Device-level is the sum value of tiles for multi-tiles.
    # 7. GPU Memory Write (kB/s), per tile or device. Device-level is the sum value of tiles for multi-tiles.
    # 18. GPU Memory Used (MiB), per tile or device. Device-level is the sum value of tiles for multi-tiles.

    # xpu-smi does not seem to be working as expected
    output = subprocess.check_output(
        [
            "xpumcli",
            "dump",
            "-t",
            "0,1",  # All tiles, 1550 have 2 tiles
            "-d",
            "-1",  # All Devices
            "-m",
            "0,1,3,5,18",  # Compute Util, Power, Temp, Mem Util
            "-n",
            "1",  # Run once
        ],
        text=True,
    )

    def parse(val, type, default):
        try:
            return type(val)
        except ValueError:
            return default

    data = []
    total_size = gpu.max_mem_alloc_size / (1024 * 1024)

    for i, line in enumerate(output.split("\n")):
        if i == 0:
            continue

        if len(line) == 0:
            continue

        (
            timestamp,
            device_id,
            tile_id,
            gpu_util,
            power,
            temp,
            mem_per,
            mem_bytes,
        ) = line.split(",")
        device_id = parse(device_id, int, 0)
        tile_id = parse(tile_id, int, 0)

        data.append(
            {
                "device": f"level_zero:{device_id * 2 + tile_id}",
                "product": gpu.name,
                "memory": {
                    "used": parse(mem_bytes, float, 0),
                    "total": total_size,
                },
                "utilization": {
                    "compute": parse(gpu_util, float, 0) / 100,
                    "memory": parse(mem_per, float, 0) / 100,
                },
                "temperature": parse(temp, float, 0),
                "power": parse(power, float, 0),
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
        # Assume all GPUs are the same
        all_gpus = query_gpu_data(self.gpus[0])

        return {i: all_gpus[i] for i in self.device_ids}

    def close(self):
        pass

    def system_info(self):
        try:
            # untested
            driver_version = "NA"
            gfx_firmware_version = "NA"
            gfx_data_firmware_version = "NA"

            output = subprocess.check_output(
                [
                    "xpumcli",
                    "dump",
                    "-t",
                    "0,1",  # All tiles, 1550 have 2 tiles
                    "-d",
                    "-1",  # All Devices
                    "-m",
                    "8,9,10",
                    "-n",
                    "1",  # Run once
                ],
                text=True,
            )
            for i, line in enumerate(output.split("\n")):
                if i == 0:
                    continue

                if len(line) == 0:
                    continue

                (
                    driver_version,
                    gfx_firmware_version,
                    gfx_data_firmware_version,
                ) = line.split(",")

            return {
                "DRIVER_VERSION": driver_version,
                "GFX_FIRMWARE_VERSION": gfx_firmware_version,
                "GFX_DATA_VERSION": gfx_data_firmware_version,
            }
        except Exception:
            import traceback

            traceback.print_exc()
            return {}
