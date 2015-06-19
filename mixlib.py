#!/usr/bin/python3
# coding=utf8

import os         as OS
import binascii   as BinASCII

import abstractio as AbstractIO
from mixtool_gtk  import messagebox

# Constants
FLAG_CHECKSUM  = 1
FLAG_ENCRYPTED = 2

TYPE_TD        = 1
TYPE_RA        = 2
TYPE_TS        = 3

MIXDB_TD       = 0
MIXDB_TS       = 0

BYTEORDER      = "little"
XCC_ID         = b"XCC by Olaf van der Spek\x1a\x04\x17\x27\x10\x19\x80"

# Instance representing a single MIX file
# Think of this like a file system driver
class MixFile:
	# Constructor opens MIX file
	def __init__(self, Stream):
		# TODO: Test stream
		self.Stream   = Stream
		self.filesize = self.Stream.seek(0, OS.SEEK_END)
		
		if self.filesize < 4:
			raise Exception("File too small")
		
		# Generic initial values
		self.compactwrite = True # True: Size optimized write; False: Speed optimized write
		
		# First two bytes are zero for RA/TS and the number of files for TD
		self.Stream.seek(0, OS.SEEK_SET)
		firstbytes = int.from_bytes(self.Stream.read(2), BYTEORDER)
		if firstbytes == 0:
			# It seems we have a RA/TS MIX so decode the flags
			flags = int.from_bytes(self.Stream.read(2), BYTEORDER)
			self.has_checksum = flags & FLAG_CHECKSUM == FLAG_CHECKSUM
			self.is_encrypted = flags & FLAG_ENCRYPTED == FLAG_ENCRYPTED
			
			# Encrypted TS MIXes have a key.ini (1983676893) we can check for later,
			# so at this point assume TYPE_TS only if unencrypted
			self.mixtype = TYPE_RA if self.is_encrypted else TYPE_TS
			
			# Get header data for RA/TS
			if self.is_encrypted:
				# OK, we have to deal with this first
				self.key_source = self.Stream.read(80)
			else:
				# RA/TS MIXes hold their filecount after the flags,
				# whilst for TD MIXes their first two bytes are the filecount.
				self.numfiles = int.from_bytes(self.Stream.read(2), BYTEORDER)
		else:
			# Maybe it's a TD MIX
			self.mixtype = TYPE_TD
			self.flags = 0
			self.has_checksum = False
			self.is_encrypted = False
			
			# Get header Data for TD
			self.numfiles = firstbytes
			
		# From here it's the same for every unencrypted MIX
		if not self.is_encrypted:
			self.bodysize = int.from_bytes(self.Stream.read(4), BYTEORDER)
			self.indexstart = self.Stream.tell()
			self.indexsize = self.numfiles * 12
			self.bodystart = self.indexstart + self.indexsize
			
			# Check if data is sane
			if self.filesize - self.bodystart != self.bodysize:
				raise Exception("Incorrect filesize or invalid header.")
				
			# OK, time to read the index
			minoffset = None
			self.index    = []
			self.contents = {}
			for i in range(0, self.numfiles):
				key    = int.from_bytes(self.Stream.read(4), BYTEORDER)
				offset = int.from_bytes(self.Stream.read(4), BYTEORDER)
				size   = int.from_bytes(self.Stream.read(4), BYTEORDER)
				
				self.index.append({"key": key, "offset": offset, "size": size, "name": None})
				self.contents[key] = self.index[i]
				
				if minoffset is None or offset < minoffset: minoffset = offset
			self.indexfree = int(minoffset / 12)
		
		
	# Get a file out of the MIX
	def get_file(name, start=0, bytes=-1):
		# Negative start counts bytes from the end
		pass
		
	def get_index(self, key):
		return self.index.index(self.contents[key]) if key in self.contents else None
		
	# Rename a file in the MIX
	def rename(old, new):
		pass
		
	# Write current index to MIX
	def write_index():
		pass
		
	# Returns a AbstractIO instance
	def open(self, file):
		if file:
			pass
			
		# TODO: Check if valid
		return AbstractIO.AbstractIO(self, self.contents["key"]["offset"], self.contents["key"]["size"])
		
	# Moves content out of the way
	def move_away(self, key):
		# Write new content to holes if at least 2M free
		# Move content to holes if big enough
		# Leave at least 1M for index, move away first file when file is added
		# If running out of space while writing content, check if current or 
		pass
		
	def fstat(self):
		# Returns information on a file contained
		pass
		
	# Compact mix function // Works like defragmentation
	# Reorganizing orders contents by size with the smallest at that beginning
	def compact(self, reorganize=False):
		pass
		
	# Return current Local Mix Database file
	def get_mixdb(self):
		pass
		

class MixError(Exception):
	# Error Class
	pass

# Create MIX-Identifier from filename
# Thanks to Olaf van der Spek for providing these functions
def get_key(name, mixtype):
	name   = name.upper()
	name   = name.replace("/", "\\\\")
	name   = name.encode("windows-1252", "replace")
	length = len(name)
	
	if mixtype == TYPE_TS:
		# Compute a key for TS MIXes
		a = length & ~3
		if length & 3:
			name += bytes((length - a,))
			name += bytes((name[a],)) * (3 - (length & 3))
		return BinASCII.crc32(name) & 4294967295
	else:
		# Compute a key for TD/RA MIXes
		i   = 0
		key = 0
		while i < length:
			a = 0
			for j in range(0, 4):
				a >>= 8
				if i < length:
					a |= (name[i] << 24)
					i += 1					
			key = (key << 1 | key >> 31) + a & 4294967295
		return key
