from numpy import *
import time

class OperationPoint():
	def __init__(self, G = 0., I = 0., Pp = 0., Fp =0. ):
		self.I = I
		self.Pp  = Pp
		self.Fp = Fp
		self.G = G

class TuningTable():
	def __init__(self, points = []):
		self.i = 0
		self.I = array([])
		self.Pp = array([])
		self.Fp = array([])
		self.G = array([])
		if hasattr(points, "__len__"):
			if len(points):
				for op in points:
					self.add_point(op)
		else:
			self.add_point(points)
	
	def __iter__(self):
		self.i=0
		return self
		
	def __next__(self):
		if self.i < len(self.I):
			i=self.i
			self.i+=1
			return OperationPoint(G = self.G[i], I = self.I[i], Pp = self.Pp[i], Fp =self.Fp[i] )
		else:
			self.i=0
			raise StopIteration			
	
	def add_point(self,op):
		self.I = hstack( [self.I, op.I] )
		self.Pp = hstack( [self.Pp, op.Pp] )
		self.Fp = hstack( [self.Fp, op.Fp] )
		self.G = hstack( [self.G, op.G] )
	
	def dump(self, path):
		data = vstack( ( self.G, self.Fp, self.Pp, self.I ) ).T	
		savetxt(path, data, header = "G\t Fp\t Pp\t I")
	
	def load(self, path):
		data = loadtxt(path).T
		self.G = data[0]
		self.Fp = data[1]
		self.Pp = data[2]
		self.I = data[3]
	
	def ind(self,i):
		return OperationPoint(G = self.G[i], I = self.I[i], Pp = self.Pp[i], Fp =self.Fp[i] )

	def to_dict(self):
		return {'G':self.G,'Fp':self.Fp, 'Pp':self.Pp,'I':self.I}

class JpaTuner():
	def __init__(self, vna = None, pump = None, bias = None ):
		self.vna = vna
		self.pump = pump
		self.bias = bias
		
		self.I0 = 0.
		self.I05 = 1e-3
		self.dIraw = 0.02e-3
		self.dIfine = 0.001e-3
		
		self.Pp_init = -10 #dbm
		self.dPp = 0.01
		self.dPp_raw = 1.
		self.Pp_max = 17.
		self.Gthr = 3 #db
		
		self.dF = 1e6 #Signal detuning from Fp/2
		
		self.Ps = -50
		self.bw = 100
		
		self.Npoints = 500
		
		self.max_it = 100

	def meas_S21(self):
		data = self.vna.get_tracedata(format = 'REALIMAG')
		return (data[0]+1.j*data[1])
	
	#Finds right magnetic bias and pump power for specified gain at specified frequency
	#G - gain in dB
	#F - signal frequency
	def find_gain(self, G, F):	
	
		Glin = 10**(G/20)
		Fp = F*2.
		
		self.bias.set_status( 1 )
		self.pump.set_power( self.Pp_init )
		Pp = self.Pp_init
		self.pump.set_frequency( Fp )
		
		self.vna.set_sweep_mode('cw')
		self.vna.set_frequency( F + self.dF )
		
		self.vna.set_bandwidth( self.bw )
		self.vna.set_power( self.Ps )
		
		self.vna.pre_sweep()
		self.pump.set_status(0)
		time.sleep(0.05)
		print("Refrence measurement...")
		self.vna.set_nop(self.Npoints)
		S21_ref = self.meas_S21().mean()
		print("S21_ref = {:.2f} dB".format(20*log10(abs(S21_ref)) ))
		self.vna.set_nop(1)
		
		self.pump.set_status(1)
		status=False
		print ("Raw search...")
		for I in arange(self.I0, self.I05, abs(self.dIraw)*sign(self.I05-self.I0) ):
			self.bias.set_current(I)
			time.sleep(0.03)
			S21 = self.meas_S21()[0]
			gain = abs(S21/S21_ref)
			print( "I= {:.4e}A G = {:.2f} dB".format(I, 20*log10(gain) ) , end = '\r')
			if gain > Glin:
				status = True
				break
		print("")		
		
		if status:
			Istart = I
			print("Noise measurement...")
			self.vna.set_nop(self.Npoints)
			time.sleep(0.5)
			S21 = self.meas_S21()/S21_ref
			
			sigma = std(S21)
			gain = abs(mean(S21))
			dg = 4*sigma
			if sigma>1.:
				time.sleep(0.5)
				S21 = self.meas_S21()/S21_ref
				sigma = std(S21)
				gain = abs(mean(S21))
				dg = 4*sigma
			
			self.vna.set_nop(1)
			
			print("G = {:.2f} Sigma= {:e}".format(gain,sigma) )
			print("Fine search...")
			
			Iover = Istart
			for I in arange(Istart, self.I05, self.dIfine * sign(self.I05 - self.I0) ):
				self.bias.set_current(I)
				time.sleep(0.01)
				gain = abs(self.meas_S21()[0]/S21_ref)
				print("I = {:.4e}A P = {:.2f}dBm G = {:.2f}dB".format(I, Pp, 20*log10(gain) ), end = '\r')
				while gain - Glin > dg:
					Iover = I
					Pp -= 0.01
					self.pump.set_power(Pp)
					gain = abs(self.meas_S21()[0]/S21_ref)
				if gain - Glin < -dg : break
			print("")		
			I = (I+Iover)/2
			self.bias.set_current(I)
			gain = abs(self.meas_S21()[0]/S21_ref)
			
		self.vna.post_sweep()
		
		op = OperationPoint(G = 20*log10(gain), Pp = Pp, I=I, Fp = Fp)
		
		return op, status
	
	def find_gain_sm(self, G, F):	
	
		Glin = 10**(G/20)
		Gthr_lin = 10**(self.Gthr/20)
		Fp = F*2.
		
		self.bias.set_status( 1 )
		self.pump.set_power( self.Pp_init )
		self.pump.set_frequency( Fp )
		Pp = self.Pp_init
		
		self.vna.set_sweep_mode('cw')
		self.vna.set_frequency( F + self.dF )
		
		self.vna.set_bandwidth( self.bw )
		self.vna.set_power( self.Ps )
		
		self.vna.pre_sweep()
		
		states = {'raw_search':0, 
			'stat_meas':1, 
			'max_search': 2, 
			'p_tune': 3, 
			'stop': 4, 
			'ref_meas': 5, 
			'prep_raw_search': 6, 
			'prep_max_search': 7,
			'i_tune': 8,
			'i_tune2': 9,
			'success': 10}
		
		Gmax = 1.
		Gmax_last = 1.
		Imax = 0.
		Pmax = -18
		Iover = 0.
		state = states['ref_meas']
		status = False
		n_it = 0
		while(state != states['stop']):
			if state == states['ref_meas']:
				self.pump.set_status(0)
				time.sleep(0.1)
				print("Refrence measurement...")
				self.vna.set_nop(self.Npoints)
				S21_ref = self.meas_S21().mean()
				print("S21_ref = {:.2f} dB".format(20*log10(abs(S21_ref)) ))
				self.vna.set_nop(1)
				self.pump.set_status(1)
				time.sleep(0.05)
				state = states['prep_raw_search']
				print ("Raw search...")
				
			elif state == states['prep_raw_search']:	
				Istep = abs(self.dIraw)*sign(self.I05-self.I0)
				I = self.I0
				state = states['raw_search']
				
			elif state == states['raw_search']:
				self.bias.set_current(I)
				time.sleep(0.05)
				S21 = self.meas_S21()[0]
				gain = abs(S21/S21_ref)
				print( "Raw search: P = {:.2f} dBm I= {:.4e}A G = {:.2f} dB".format(Pp, I, 20*log10(gain) ) , end = '\r')
				
				if gain >= Gthr_lin: 
					state = states['stat_meas']
					print("")
				else:
					I+=Istep
				if (I - self.I05)*sign(self.I05-self.I0) >0:
					Pp += self.dPp_raw
					if Pp>self.Pp_max:
						state = states['stop']
					else:	
						self.pump.set_power(Pp)
						state = states['prep_raw_search']
					
			elif state == states['stat_meas']:
				print("Noise measurement...")
				self.vna.set_nop(self.Npoints)
				time.sleep(0.05)
				S21 = self.meas_S21()/S21_ref
			
				sigma = std(S21)
				gain = abs(mean(S21))
				dg = 4*sigma
				print("G = {:.2f} Sigma= {:e}".format(gain,sigma) )
				self.vna.set_nop(1)
				if (gain - Gthr_lin) > dg*2:
					state = states['raw_search']
				else:
					state = states['prep_max_search']
				
			elif state == states['prep_max_search']:	
				Istep = abs(self.dIfine)*sign(self.I05-self.I0)
				Imax = I
				Gmax = gain
				state = states['max_search']	
			
			elif state == states['max_search']:
				I+= Istep
				self.bias.set_current(I)
				time.sleep(0.05)
				gain = abs(self.meas_S21()[0]/S21_ref)
				print( "Max search: I= {:.4e}A G = {:.2f} dB Gmax = {:.2f} dB".format(I, 20*log10(gain), 20*log10(Gmax) ) , end = '\r')
				if gain > Gmax:
					Gmax = gain
					Imax = I
				if Gmax-gain > dg:
					state = states['p_tune']
					I = Imax
					self.bias.set_current(I)
					print("")
			
			elif state == states['p_tune']:	
				Pp+= self.dPp
				if Pp>self.Pp_max:
					Pp-= self.dPp
					n_it+=1
				else:
					n_it = 0
				
				if n_it > self.max_it:
					state = states['stop']
				
				self.pump.set_power(Pp)
				time.sleep(0.05)
					
				gain = abs(self.meas_S21()[0]/S21_ref)
				if gain > Gmax:
					Gmax = gain
					Imax = I
					Pmax = Pp
				print( "Power optimization:P = {:.2f} dBm G = {:.2f} Gmax = {:.2f}".format(Pp, 20*log10(gain),log10(Gmax)*20 ) , end = '\r')
				'''
				if abs(gain - Glin)<dg:
					print('')
					state = states['success']
				'''
				if abs(gain - Gmax)> 2*dg or gain > (Glin-dg):
					print('')
					I = Imax
					Pp = Pmax
					self.pump.set_power(Pp)
					self.bias.set_current(I)
					time.sleep(0.05)
					gain = abs(self.meas_S21()[0]/S21_ref)
					Gmax = gain
					Istep = abs(self.dIfine)*sign(self.I05-self.I0)
					if abs(Gmax - Gmax_last)< dg:
						if abs(Gmax - Glin)< dg:
							state = states['success']
						else:	
							state = states['stop']
					else:
						Gmax_last = Gmax
						state = states['i_tune']
			
			elif state == states['i_tune']:
				I+= Istep
				self.bias.set_current(I)
				time.sleep(0.05)
				gain = abs(self.meas_S21()[0]/S21_ref)
				print("Itune I = {:.4e}A P = {:.2f}dBm G = {:.2f}dB".format(I, Pp, 20*log10(gain) ), end = '\r')
				while gain - Glin > dg:
					Pp -= 0.01
					self.pump.set_power(Pp)
					gain = abs(self.meas_S21()[0]/S21_ref)
					Pmax = Pp
					Gmax = gain
					Imax = I
				if gain>Gmax:
					Gmax = gain
					Imax = I
				if Gmax - gain > 2*dg :
					Istep = -Istep
					I = Imax
					Pp = Pmax
					self.pump.set_power(Pp)
					self.bias.set_current(I)
					time.sleep(0.05)
					print ('')
					state = states['i_tune2']
					
			elif state == states['i_tune2']:
				I+= Istep
				self.bias.set_current(I)
				time.sleep(0.05)
				gain = abs(self.meas_S21()[0]/S21_ref)
				print("Itune I = {:.4e}A P = {:.2f}dBm G = {:.2f}dB".format(I, Pp, 20*log10(gain) ), end = '\r')
				while gain - Glin > dg:
					Iover = I
					Pp -= 0.01
					self.pump.set_power(Pp)
					gain = abs(self.meas_S21()[0]/S21_ref)
					Pmax = Pp
					Gmax = gain
					Imax = I
				if gain>Gmax:
					Gmax = gain
					Imax = I
				if Gmax - gain > 2*dg :
					I = Imax
					Pp = Pmax
					self.pump.set_power(Pp)
					self.bias.set_current(I)
					time.sleep(0.05)
					print('')
					if abs(Gmax - Glin)< dg:
						state = states['success']
					else:	
						state = states['p_tune']
					
			elif state == states['success']:
				status = True
				gain = abs(self.meas_S21()[0]/S21_ref)
				break
				
		self.vna.post_sweep()
		
		op = OperationPoint(G = 20*log10(gain), Pp = Pp, I = I, Fp = Fp)
		
		return op, status	
	
	def set_op(self,op):
		self.bias.set_current(op.I)
		self.pump.set_frequency( op.Fp )
		self.pump.set_power(op.Pp)
	
	def vna_snapshot(self, op, span, N = None, Ps = None, bw = None):
		if N is None:
			N = self.Npoints
		if Ps is None:
			Ps = self.Ps	
		self.bias.set_current(op.I)
		self.bias.set_status(1)
		
		self.pump.set_power(op.Pp)
		self.pump.set_status(1)
		self.pump.set_frequency( op.Fp )
		
		self.vna.set_nop(N)
		self.vna.set_power(Ps)
		self.vna.set_sweep_mode('lin')
		self.vna.set_centerfreq( op.Fp/2 )
		self.vna.set_span( span )
		if bw is None:
			self.vna.set_bandwidth(self.bw)
		else:
			self.vna.set_bandwidth(bw)
		
		self.vna.pre_sweep()
		S21on = self.meas_S21()
		self.pump.set_status(0)
		S21off = self.meas_S21()
		Fpoints = self.vna.get_freqpoints()
		self.vna.post_sweep()
		
		return S21on, S21off, Fpoints
		
		