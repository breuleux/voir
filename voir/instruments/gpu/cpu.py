def is_installed():
    return True


class DeviceSMI:
    def get_gpus_info(self):
        return {}

    @property
    def arch(self):
        return "cpu"

    @property
    def visible_devices():
        return ""

    def close(self):
        pass
