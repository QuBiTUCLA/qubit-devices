from labscript import *

# Import classes needed for the devices which will be used
from archive.labscript_devices import DummyPseudoclock
from archive.labscript_devices import FeatherInterfaceBoard


DummyPseudoclock(name='dummy_clock',BLACS_connection='dummy')

FeatherInterfaceBoard(name='board', com_port='COM3', parent_device=dummy_clock.clockline, mock=False)

ai = AnalogIn(name='anain', parent_device=board)

# The following is standard boilerplate necessary for the file to compile
if __name__ == '__main__':

   start()

   stop(1)
