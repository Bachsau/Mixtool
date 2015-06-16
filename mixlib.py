#!/usr/bin/python3

import os as OS
#import io as IO

import abstractio as AbstractIO

# Constants
FLAG_CHECKSUM  = 1
FLAG_ENCRYPTED = 2

TYPE_TD        = 1
TYPE_RA        = 2
TYPE_TS        = 3

MIXDB_TD       = 0
MIXDB_TS       = 0

# Instance representing a single MIX file
# Think of this like a file system driver
class MixFile:
	# Constructor opens MIX file
	def __init__(self, Stream):
		# TODO: Test stream
		self.Stream = Stream
		
		# Generic initial values
		self.compactwrite = True # True: Size optimized write; False: Speed optimized write
		
		# First two bytes are zero for RA/TS and the number of files for TD
		firstbytes = int.from_bytes(self.Stream.read(2), 'little')
		if firstbytes == 0:
			# It seems we have a TS MIX so decode the flags
			self.type = TYPE_TS
			self.flags = int.from_bytes(self.Stream.read(2), 'little')
			self.has_checksum = (True if self.flags & FLAG_CHECKSUM == FLAG_CHECKSUM else False)
			self.is_encrypted = (True if self.flags & FLAG_ENCRYPTED == FLAG_ENCRYPTED else False)
			
			# Get header data for RA/TS
			if self.is_encrypted:
				# FUCK. We have to handle this shit
				self.key_source = self.Stream.read(80)
			else:
				# Easy going
				self.numfiles = int.from_bytes(self.Stream.read(2), 'little')
		else:
			# Maybe it's a TD or RA MIX
			self.type = TYPE_TD
			self.flags = 0
			self.has_checksum = False
			self.is_encrypted = False
			
			# Get header Data for TD
			self.numfiles = firstbytes
			
		# From here it's the same for every unencrypted MIX
		if not self.is_encrypted:
			self.bodysize = int.from_bytes(self.Stream.read(4), 'little')
			self.indexstart = self.Stream.tell()
			self.indexsize = 12 * self.numfiles
			self.bodystart = self.indexstart + self.indexsize
			
			# Let's check those header data against reality
			self.filesize = self.Stream.seek(0, OS.SEEK_END)
			if self.filesize - self.bodystart != self.bodysize:
				raise Exception("Incorrect filesize")
				
			# OK, time to read the index
			self.Stream.seek(self.indexstart)
			self.contents = {}
			for index in range(0, self.numfiles):
				key    = int.from_bytes(self.Stream.read(4), 'little')
				offset = int.from_bytes(self.Stream.read(4), 'little')
				size   = int.from_bytes(self.Stream.read(4), 'little')
				
				self.contents[key] = {"offset": offset, "size": size, "index": index, "name": None}
			
		
	# Returns an AbstractIO instance
	def open_by_name(self):
		# Search a names dict, use genid if not found
		pass
	
	# Returns a AbstractIO instance
	def open_by_key(self):
		# TODO: Check if valid
		return AbstractIO.AbstractIO(self, self.contents["key"]["offset"], self.contents["key"]["size"])
		
	def fstat(self):
		# Returns information on a file contained
		pass
		
	# Compact mix function // Works like defragmentation
	def compact(self, reorganize = False):
		pass
		
	# Return current Local Mix Database file
	def get_mixdb(self):
		pass
		

class MixError(Exception):
	# Error Class
	pass

# Hash function to create MIX-Identifier from filename
def genid(name, type):
	if type != TYPE_TS:
		pass
	else:
		pass
