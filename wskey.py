#!/usr/bin/python3
# coding=utf8

from array import array
from mixtool_gtk import messagebox

# Constants
PUBKEY   = b"AihRvNoIbTn85FZRYNZRcT+i6KpU+maCsEqr3Q5q+LDB5tH7Tz2qQ38V"
CHAR2NUM = (-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 62, -1, -1, -1, 63,
            52, 53, 54, 55, 56, 57, 58, 59, 60, 61, -1, -1, -1, -1, -1, -1,
            -1,  0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14,
            15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, -1, -1, -1, -1, -1,
            -1, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40,
            41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1)

# struct bignum
class bignum(array):
	__slots__ = ()
	initbytes = bytes(2048)
	def __new__(cls):
		return array.__new__(cls, "L", self.initbytes)

# static struct 
# {
#   bignum key1;
#   bignum key2;
#   uint32_t len;
# } pubkey;
class WSKey:
	# static void init_pubkey()
	def __init__(self):
		self.key1 = bignum()
		self.key2 = bignum()
		self.len_ = 0
		
		self.init_bignum(self.key2, 0x10001, 64)
		keytmp = bytearray(256)
		i2 = 0
		for i in range(0, len(PUBKEY), 4):
			tmp = CHAR2NUM[PUBKEY[i]]
			tmp <<= 6; tmp |= CHAR2NUM[PUBKEY[i + 1]]
			tmp <<= 6; tmp |= CHAR2NUM[PUBKEY[i + 2]]
			tmp <<= 6; tmp |= CHAR2NUM[PUBKEY[i + 3]]
			keytmp[i2] = (tmp >> 16) & 0xff
			keytmp[i2 + 1] = (tmp >> 8) & 0xff
			keytmp[i2 + 2] = tmp & 0xff
			i2 += 3
		self.key_to_bignum(self.key1, keytmp, 64);
		self.len_ = self.bitlen_bignum(self.key1, 64) - 1;
		
	def bitlen_bignum(self, num, len_):
		ddlen = self.len_bignum(num, len_)

		if ddlen == 0:
			return 0
			
		bitlen = ddlen * 32;
		mask = 0x80000000;
		while (mask & num[ddlen - 1]) == 0:
			mask >>= 1
			bitlen -= 1
		return bitlen

	def len_bignum(self, num, len_):
		i = len_ - 1
		while i >= 0 and num[i] == 0:
			i -= 1
		return i + 1
		
	def key_to_bignum(self, num, key, len_):
		if key[0] != 2:
			return
			
		if key[1] & 0x80:
			keylen = 0;
			for i in range(key[1] & 0x7f):
				keylen = (keylen << 8) | key[i+2]
			keyptr = (key[1] & 0x7f) + 2
		else :
			keylen = key[1]
			keyptr = 2
			
		if keylen <= len_ * 4:
			self.move_key_to_big(num, key, keyptr, keylen, len_)
			
	def move_key_to_big(self, num, key, keyptr, keylen, blen):
		sign = 0xff if key[keyptr] & 0x80 else 0
		start = blen * 4
		for i in range(start, keylen, -1):
			num[i - 1] = sign;
		for i in range(start, 0, -1):
			num[i - 1] = key[keylen + keyptr - i]
			
	def init_bignum(self, num, val, len_):
		num[:len_ * 4] = array("L", bytes(len_ * 32))
		num[0] = val
		
	def calc_a_key(self, n1, n2, n3, n4, len_):
		n_tmp = bignum()
		self.init_bignum(n1, 1, len_);
		n4_len = self.len_bignum(n4, len_)
		#init_two_dw(n4, n4_len)
		
		
	def process_predata(self, pre):
		# pre is keysource
		buf = bytearray(256)
		
		a = int((self.len_ - 1) / 8)
		pre_len = (55 / a + 1) * (a + 1)
		n2 = bignum()
		n3 = bignum()
		while a + 1 <= pre_len:
			self.init_bignum(n2, 0, 64)
			n2[:a + 1] = array("L", pre)[:a + 1]
			self.calc_a_key(n3, n2, self.key2, self.key1, 64);
		
			#memmove(buf, n3, a);
		
			#pre_len -= a + 1;
			#pre += a + 1;
			#buf += a;

		
# Startknopf!
def get_blowfish_key(keysource, output):
	PubKey = WSKey()
	result = PubKey.process_predata(keysource);

# Just testing
temp_output = bytearray(56)
temp_source = b'W\xab\x0c\x0e\xb3D\xf3\n\xf2\x81*\xc0X\xa5]q\xd0\xaf\x86\xf5\xf0\xf3\xd9Q\x0e\x98\xf2;\xac]l\xff\xde]\xb2&.\t\xb6P\xd5|\x1cq\x82\x12\x03I\xdb(\xe0\x9dB\x96\x92\x06\x1d:\x90 \x1e~\xa8\xdf\x0fPU\xce\xc6;v\xffg\x11W"\x01A;*'
get_blowfish_key(temp_source, temp_output)




glob1_bitlen    = 0
glob1_len_x2    = 0
glob2           = 0
glob1_hi        = 0
glob1_hi_inv    = 0
glob1_hi_bitlen = 0
glob1_hi_inv_lo = 0
glob1_hi_inv_hi = 0



		


