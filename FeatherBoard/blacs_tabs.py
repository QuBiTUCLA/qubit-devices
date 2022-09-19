from blacs.device_base_class import DeviceTab

class FeatherBoardGuilessTab(DeviceTab):
    def initialise_GUI(self):
        pass

    def get_save_data(self):
        return {}

    def restore_save_data(self, save_data):
        pass

    def initialise_workers(self):
        # Create and set the primary worker
        self.address = str(
            self.settings['connection_table'].find_by_name(self.settings["device_name"]).BLACS_connection)
        self.create_worker("main_worker","user_devices.blacs_worker.GuilessWorker", {"address": self.address})
        self.primary_worker = "main_worker"

