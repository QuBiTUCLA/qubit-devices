# A labscript device class for data acquisition boards made by Alazar Technologies Inc (ATS)
# Hacked up from NIboard.py by LDT 2017-01-26
#
# Copyright (c) Monash University 2017

from labscript import Device, AnalogIn,LabscriptError, set_passed_properties
import numpy as np



class FeatherBoard(Device):
    allowed_children = [AnalogIn]
    description = 'Feather Board'

# Many properties not supported. Examples include:
# SetDataFormat
# Anything to do with board memory
# Anything "for scanning"
    @set_passed_properties(property_names={
        "device_properties": ["acquisition_rate", "com_port"]
    })
    def __init__(self, name, acquisition_rate=250, com_port=""):
        if com_port == "":
            raise LabscriptError("please specify comport for Feather Board")
        Device.__init__(self, name, None, com_port)
        self.BLACS_connection = com_port
        self.name = name
        self.acquisition_rate = acquisition_rate
        # This line makes BLACS think the device is connected to something

    def add_device(self, output):
        # TODO: check there are no duplicates, check that connection
        # string is formatted correctly.
        Device.add_device(self, output)

    # Has no children for now so hopefully does nothing
    def generate_code(self, hdf5_file):
        Device.generate_code(self, hdf5_file)
        inputs = {}
        for device in self.child_devices:
            if isinstance(device, AnalogIn):
                inputs[device.connection] = device
            else:
                raise Exception('Got unexpected device.')
        input_connections = sorted(inputs)
        input_attrs = []
        acquisitions = []
        for connection in input_connections:
            input_attrs.append(self.name+'/'+connection)
            for acq in inputs[connection].acquisitions:
                acquisitions.append((connection, acq['label'], acq['start_time'],
                                     acq['end_time'], acq['wait_label'], acq['scale_factor'], acq['units']))
        acquisitions_table_dtypes = [('connection', 'a256'), ('label', 'a256'), ('start', float),
                                     ('stop', float), ('wait label', 'a256'), ('scale factor', float), ('units', 'a256')]
        acquisition_table = np.empty(
            len(acquisitions), dtype=acquisitions_table_dtypes)
        for i, acq in enumerate(acquisitions):
            acquisition_table[i] = acq
            grp = self.init_device_group(hdf5_file)
        if len(acquisition_table):  # Table must be non empty
            grp.create_dataset(
                'ACQUISITIONS', data=acquisition_table)
            self.set_property('analog_in_channels',', '.join(
                input_attrs), location='device_properties')
