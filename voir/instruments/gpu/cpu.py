def is_installed():
    return True


class DeviceSMI:
    def get_gpus_info(self, selection=None):
        return {}

    @property
    def arch(self):
        return "cpu"

    @property
    def visible_devices(self):
        return ""

    def close(self):
        pass

    def system_info(self):
        return {}
