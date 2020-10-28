import sys

# python version check
if sys.version_info.major < 3:
	raise RuntimeError("Python3 or newer required")
#end if

"""
DCF77 decoder
(c) Jan Willem ON6LM

This software is open-source licensed under the GPL3.0-or-later license:
https://www.gnu.org/licenses/gpl-3.0-standalone.html

This piece of code is designed to work with the output of the corresponding
GNU radio flow, where the input is a stream of bytes, one bit per byte meaning
either high (1) or low (0).

Given the sample rate, it will then decode the time.

This will read from a udp multicast address by default, which makes
it easy to work with.

For decoding the byte stream, it will first get converted to run length encoding,
to make it easier to work with. Given the sample rate, it will then search for the
longer gap of '1' which indicates the start of the message. A short (~100ms) burst
of '0' means a logical 0, a burst of ~200ms means a logical 1.

After that conversion, it's just a matter of decoding the bitpattern.

Check the table at https://en.wikipedia.org/wiki/DCF77#Time_code_interpretation for
more information.
"""

import socket
import struct

class decoder:
	def __init__(self, lip, lport, sample_rate):
		self.lip = lip
		self.lport = lport
		self.sample_rate = sample_rate

		self.start_level = 0
		self.decoded = []
		# TODO: this was used for testing, clean up and write decent unit tests
		# self.decoded = [
		# 	0,0,0,0,1, 1,1,0,0,0,
		# 	1,0,1,1,1, 0,0,1,0,0,
		# 	1,1,1,0,0, 0,0,1,1,0,
		# 	0,0,0,0,0, 0,1,0,0,1,
		# 	0,1,0,1,0, 1,0,0,1,0,
		# 	0,0,0,0,0, 1,0,0,1]
		# self.decodeCdf()

	def listen(self):
		lip = self.lip
		lport = self.lport

		# receiving multicast in python, shamelessly stolen from
		# https://stackoverflow.com/questions/603852/how-do-you-udp-multicast-in-python

		# assert bind_group in groups + [None], \
		#     'bind group not in groups to join'
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

		# allow reuse of socket (to allow another instance of python to run this
		# script binding to the same ip/port)
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

		sock.bind(('',lport)) # bind to any ip-address

		#igmp join
		mreq=struct.pack('4sl',socket.inet_aton(lip),socket.INADDR_ANY)
		sock.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,mreq)

		self.network_buf=[]
		while True:
			#receive data
			newbytes = sock.recv(10240)

			for inbyte in struct.unpack('B'*len(newbytes),newbytes):
				self.network_buf.append(inbyte)
			consumed = self.runlength_encode(self.network_buf)
			self.network_buf = self.network_buf[consumed:]

	def runlength_encode(self, buf):
		"""
		Reads buf and appends result to runlength_buf.
		Returns the number of items to remove from buf.
		"""
		toRemove = 0
		start_pos = 0

		while True:
			value = 0 if self.start_level == 1 else 1

			try:
				pos = self.network_buf.index(self.start_level, start_pos)

				self.handle_runlength(value, pos - start_pos)
				self.start_level = value
				start_pos = pos
				toRemove += pos
			except ValueError as err:
				# need more data
				return toRemove

	def handle_runlength(self, value, length):
		"""
		Decode the bits:
		If 1 longer than sample_rate: start of sequence
		otherwise ignore the 1s.
		If 0 longer than 0.15*sample_rate: 1, else 0
		"""
		if value == 1 and length > self.sample_rate:
			self.decoded = []
		if value == 0:
			decoded_value = 1 if length > .15*self.sample_rate else 0
			self.decoded.append(decoded_value)
		self.decodeCdf()

	def decodeCdf(self):
		if len(self.decoded) != 59:
			return

		self.checkParity1()
		self.checkParity2()
		self.checkParity3()

		tz = self.parseTz()
		m = self.parseMinutes()
		h = self.parseHours()
		d = self.parseDayOfMonth()
		wd = self.parseDayOfWeek()
		M = self.parseMonth()
		y = self.parseYear()
		print("%s %2d %s %4d %02d:%02d:%02d %s" % (wd, d, M, y, h, m, 0, tz))

	def parseTz(self):
		cestFlag = self.decoded[17]
		cetFlag = self.decoded[18]
		if cestFlag:
			return 'CEST'
		if cetFlag:
			return 'CET'
		raise ValueError("Could not parse timezone, got %d and %d as tz bits" % (cestFlag, cetFlag))

	def parseMinutes(self):
		minutes = 0
		minutes += self.decoded[21] * 1
		minutes += self.decoded[22] * 2
		minutes += self.decoded[23] * 4
		minutes += self.decoded[24] * 8
		minutes += self.decoded[25] * 10
		minutes += self.decoded[26] * 20
		minutes += self.decoded[27] * 40
		return minutes

	def parseHours(self):
		hours = 0
		hours += self.decoded[29] * 1
		hours += self.decoded[30] * 2
		hours += self.decoded[31] * 4
		hours += self.decoded[32] * 8
		hours += self.decoded[33] * 10
		hours += self.decoded[34] * 20
		return hours

	def parseDayOfMonth(self):
		day = 0
		day += self.decoded[36] * 1
		day += self.decoded[37] * 2
		day += self.decoded[38] * 4
		day += self.decoded[39] * 8
		day += self.decoded[40] * 10
		day += self.decoded[41] * 20
		return day

	def parseDayOfWeek(self):
		days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
		day = 0
		day += self.decoded[42] * 1
		day += self.decoded[43] * 2
		day += self.decoded[44] * 4
		if day < 1 or day > 7:
			raise ValueError("Invalid day: %d" % day)

		return days[day - 1]

	def parseMonth(self):
		month = 0
		month += self.decoded[45] * 1
		month += self.decoded[46] * 2
		month += self.decoded[47] * 4
		month += self.decoded[48] * 8
		month += self.decoded[49] * 10
		months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
		if month < 1 or month > 12:
			raise ValueError('Invalid month: %d' % month)

		return months[month-1]

	def parseYear(self):
		year = 0
		year += self.decoded[50] * 1
		year += self.decoded[51] * 2
		year += self.decoded[52] * 4
		year += self.decoded[53] * 8
		year += self.decoded[54] * 10
		year += self.decoded[55] * 20
		year += self.decoded[56] * 40
		year += self.decoded[57] * 80
		return year + 2000

	def checkParity1(self):
		parity = sum(self.decoded[21:28])
		if parity % 2 != self.decoded[28]:
			raise ValueError("Parity error decoding minutes")

	def checkParity2(self):
		parity = sum(self.decoded[29:35])
		if parity % 2 != self.decoded[35]:
			print(self.decoded[29:36])
			raise ValueError("Parity error parsing hours")

	def checkParity3(self):
		parity = sum(self.decoded[36:58])
		if parity % 2 != self.decoded[58]:
			raise ValueError('Parity error P3')

def Main():
	ipaddr="225.0.0.1"
	port=10000
	sample_rate=1200
	d = decoder(lip=ipaddr,lport=port,sample_rate=sample_rate)
	d.listen()

if __name__ == "__main__": Main()