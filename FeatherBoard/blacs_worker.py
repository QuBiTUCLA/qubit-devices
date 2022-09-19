import numpy as np
import time
import serial
import adafruit_board_toolkit.circuitpython_serial
from labscript_utils import properties

from labscript import LabscriptError
from blacs.tab_base_classes import Worker


class GuilessWorker(Worker):

    def init(self):
        global h5py
        import labscript_utils.h5_lock
        import h5py
        from queue import Queue
        import threading

        # print(self.connection)
        print("FeatherBoard Magnet Sensor startup sequence")

        comport_to_use = None
        comports = adafruit_board_toolkit.circuitpython_serial.data_comports()
        comports_string = ""
        for i, port in enumerate(comports):
            comports_string += port.description + ","
            if port.device.upper() == self.address.upper():
                comport_to_use = port
        comports_string = comports_string.rstrip(",")
        if comport_to_use is None:
            raise LabscriptError("There is no Featherboard connected to the selected comport "+self.address
                                 +". Available devices are at " + comports_string
                                 + ". Please change accordingly in the Connection Table.")

        print("Connecting to device on port", comport_to_use.device, comport_to_use.description)

        self.device = serial.Serial(comport_to_use.device, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=1, xonxoff=0,
                                    rtscts=0)


        self.device.write(b'go-trm\n')
        # time.sleep(1)
        trm_ok = self.device.readline().decode("utf-8").rstrip()
        if trm_ok == "roger-trm" or trm_ok == '':
            print('board connected')

        # Multiprocessing init
        self.acquisition_queue = Queue()
        self.acquisition_thread = threading.Thread(
            target=self.acquisition_loop)
        self.acquisition_thread.daemon = True
        self.acquisition_exception = None
        self.acquisition_done = threading.Event()
        self.acquisition_thread.start()
        self.aborting = False



    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        self.h5file = h5file  # We'll need this in transition_to_manual
        self.device_name = device_name
        with h5py.File(h5file, 'r') as hdf5_file:
            print("\nUsing "+h5file)
            self.param = properties.get(
                hdf5_file, device_name, 'device_properties')
            acquisition_dataset = hdf5_file['/devices/' + self.device_name + '/ACQUISITIONS']
            self.acq_start_time = acquisition_dataset.fields("start")[0]
            self.acq_stop_time = acquisition_dataset.fields("stop")[0]


        start_time = time.time()
        acq_time = self.acq_stop_time - self.acq_start_time
        acq_rate = self.param['acquisition_rate']
        acq_string = str(int(acq_time)) + ' ' + str(acq_rate)
        print("starting acquisition (time, rate): ", acq_time, acq_rate)
        self.all_data = np.empty(0, dtype=np.float32)
        self.aborting = False
        self.acquisition_queue.put('start')
        self.device.flushInput()
        self.device.flushOutput()
        self.device.write(b'g-mag-all ' + bytes(acq_string, "utf-8") + b'\n')
        return {}  # ? Check this

    # This becomes a long-running thread which fills the buffers allocated in the main thread.
    # Buffers are saved and freed in transition_to_manual().
    def acquisition_loop(self):
        while True:
            command = self.acquisition_queue.get()
            assert command == 'start'
            #print("acquisition thread: starting new acquisition")
            # This is a fresh trip through the acquisition loop, no exception has occurred yet!
            self.acquisition_exception = None
            self.acquisition_done.clear()      # I don't understand why this is needed here!

            try:
                # print("Capturing {:d} buffers. ".format(
                #     self.buffersPerAcquisition), end="")
                buffersCompleted = 0
                bytesTransferred = 0
                time.sleep(0.2)
                print('Read buffer:', end="")
                while not self.aborting:
                    self.receiveData()
                self.receiveData()
            except Exception as e:
                print(e)
                continue  # Next iteration of the infinite loop, wait for next acquisition, or have the main thread decide to die
            finally:
                self.acquisition_done.set()
            if self.aborting:
                print("acquisition thread: capture aborted.")
                break

    def program_manual(self, values):
        return values

    def receiveData(self):
        terminator = bytes('STOPACQUISITION', 'utf-8')
        raw_response = self.device.read_until(terminator)
        lenth_terminator = len(terminator)
        response = raw_response[:-lenth_terminator]
        print(str(len(response)))
        data = np.frombuffer(response, dtype=np.float32)
        print(str(len(data)))
        print("receive stuff")
        if len(data) == 0:
            print("no data received, continue")
        else:
            print("lenth " + str(len(data)))
            self.all_data = np.append(self.all_data, data)


    # This helper function waits for the acquisition_loop thread to finish the acquisition,
    # either successfully or after an exception.
    # It is used by transition_to_manual() and abort().
    # The acquisition_done flag should already be set,
    # if it can't get this after a brief delay then something has gone wrong with acquisition overrun and it will complain and die in the main thread,
    # causing the whole lot to die.
    def wait_acquisition_complete(self):
        try:
            if not self.acquisition_done.wait(timeout=2) and not self.aborting:
                raise Exception(
                    'Waiting for acquisition to complete timed out')
            #print("acquisition_exception is {:s}".format(self.acquisition_exception))
            if self.acquisition_exception is not None and not self.aborting:
                raise self.acquisition_exception
        finally:
            # This ensures that the blocking call in the acquisition thread is aborted.
            self.acquisition_done.clear()
            self.acquisition_exception = None

    def transition_to_manual(self):
        #print("transition_to_manual: using " + self.h5file)
        # Waits on the acquisition thread, and manages the lock
        self.aborting = True
        self.wait_acquisition_complete()
        # Write data to HDF5 file
        with h5py.File(self.h5file, 'r+') as hdf5_file:
            acquisition_dataset = hdf5_file['/devices/' + self.device_name + '/ACQUISITIONS']
            label = acquisition_dataset.fields("label")[0].decode("utf-8")
            print("my loop")
            start_time = np.float32(acquisition_dataset.fields("start")[0])
            try:
                grp = hdf5_file.create_group('/data/traces/')
            except ValueError as e:
                # if group exists, other process was faster
                grp = hdf5_file['/data/traces/']
                print(e)
            except Exception as e:
                raise e
            all_data_shape =  (int(len(self.all_data) / 4), 4)
            self.all_data.shape = all_data_shape
            print(self.all_data.shape)
            # self.all_data = np.array(self.all_data)
            # col = self.all_data[:,0]
            # print(col.shape)
            # print(col[1:5])
            time_series = self.all_data[:,0]
            bx = self.all_data[:,1]
            by = self.all_data[:,2]
            bz = self.all_data[:,3]
            # print(self.all_data[1:3,:])

            # 0.27 S is the time that the Featherboard usually needs to setup a measurement.
            time_series = time_series - 0.27

            dtypes = [('t', np.float64), ('values', np.float32)]

            x_row = np.empty(len(time_series), dtype=dtypes)
            x_row['t'] = time_series
            x_row['values'] = bx

            y_row = np.empty(len(time_series), dtype=dtypes)
            y_row['t'] = time_series
            y_row['values'] = by

            z_row = np.empty(len(time_series), dtype=dtypes)
            z_row['t'] = time_series
            z_row['values'] = bz

            print("gonna create group with label "+label)
            time_grp = grp.create_dataset(name = label+'_t', data=time_series)
            magnet_x = grp.create_dataset(name = label+'_b_x', data=x_row)
            magnet_y = grp.create_dataset(name = label+'_b_y', data=y_row)
            magnet_z = grp.create_dataset(name = label+'_b_z', data=z_row)
            self.device.flushInput()
            self.device.flushOutput()

        print('done.')
        return True

    def abort(self):
        print("aborting! ... ")
        self.aborting = True
        self.wait_acquisition_complete()
        self.aborting = False
        print("abort complete.")
        return True

    def abort_buffered(self):
        print("abort_buffered: ...")
        return self.abort()

    def abort_transition_to_buffered(self):
        print("abort_transition_to_buffered: ...")
        return self.abort()

    def shutdown(self):
        if self.aborting:
            print('Shutdown requested during abort; waiting 10 seconds.')
            start = time.clock()
            while self.aborting and time.clock() - start < 10:
                time.sleep(0.5)
        if self.aborting:
            print('Proceeding in lieu of complete abort.')
        return