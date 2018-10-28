from numpy import *
import sys
qt_dir = "D:/qtlab_replacement"
sys.path.append(qt_dir)
import init
from instruments import *
import sweep
import time
import save_pkl

#Data mamagement
Data_dir ="D:/Abramov/data" 
path = save_pkl.mk_dir(root = Data_dir)
print("Saving files to: ",path)

currents = arange(-1.,1, 0.02)*1e-3

pna_preset = True

cs = Yokogawa_GS210(address='GPIB0::2::INSTR')
pna = Agilent_N5242A('pna', address = 'pna')
cs.set_range(0.01)
if pna_preset:
	pna.set_nop(500)
	pna.set_power(-50.)
	pna.set_bandwidth(400)
	pna.set_centerfreq(6.87656e9)
	pna.set_span(100e6)

cs.set_status(1)
sweep.sweep(pna, (currents, cs.set_current, 'Current'))
cs.set_status(0)
pna.close()