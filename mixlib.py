#!/usr/bin/python3
# coding=utf8

import os         as OS
import binascii   as BinASCII

import abstractio as AbstractIO
from mixtool_gtk  import messagebox


# Constants
FLAG_CHECKSUM  = 1
FLAG_ENCRYPTED = 2

TYPE_TD  = 0
TYPE_RA  = 1
TYPE_TS  = 2

DBKEYS   = 1422054725,  913179935
KEYFILE  = 1983676893

ENCODING = "windows-1252"
XCC_ID = b"XCC by Olaf van der Spek\x1a\x04\x17\x27\x10\x19\x80\x00"


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
		firstbytes = int.from_bytes(self.Stream.read(2), "little")
		if firstbytes == 0:
			# It seems we have a RA/TS MIX so decode the flags
			flags = int.from_bytes(self.Stream.read(2), "little")
			self.has_checksum = flags & FLAG_CHECKSUM == FLAG_CHECKSUM
			self.is_encrypted = flags & FLAG_ENCRYPTED == FLAG_ENCRYPTED
			
			# Encrypted TS MIXes have a key.ini we can check for later,
			# so at this point assume TYPE_TS only if unencrypted
			self.mixtype = TYPE_RA if self.is_encrypted else TYPE_TS
			
			# Get header data for RA/TS
			if self.is_encrypted:
				# OK, we have to deal with this first
				self.key_source = self.Stream.read(80)
			else:
				# RA/TS MIXes hold their filecount after the flags,
				# whilst for TD MIXes their first two bytes are the filecount.
				self.filecount = int.from_bytes(self.Stream.read(2), "little")
		else:
			# Maybe it's a TD MIX
			self.mixtype = TYPE_TD
			self.flags = 0
			self.has_checksum = False
			self.is_encrypted = False
			
			# Get header Data for TD
			self.filecount = firstbytes
			
		# From here it's the same for every unencrypted MIX
		if not self.is_encrypted:
			self.bodysize = int.from_bytes(self.Stream.read(4), "little")
			self.indexstart = self.Stream.tell()
			self.indexsize = self.filecount * 12
			self.bodystart = self.indexstart + self.indexsize
			
			# Check if data is sane
			if self.filesize - self.bodystart != self.bodysize:
				raise Exception("Incorrect filesize or invalid header.")
				
			# OK, time to read the index
			minoffset = None
			self.index = []
			self.contents = {}
			for i in range(0, self.filecount):
				key    = int.from_bytes(self.Stream.read(4), "little")
				offset = int.from_bytes(self.Stream.read(4), "little")
				size   = int.from_bytes(self.Stream.read(4), "little")
				
				self.index.append({"key": key, "offset": offset, "size": size, "name": None})
				self.contents[key] = self.index[i]
				
				if minoffset is None or offset < minoffset: minoffset = offset
			self.index.sort(key=lambda i: i["offset"])
			self.indexfree = int(minoffset / 12)
			
			# Now read the Local MIX Database
			self.names = {} # Pairs of "Name: Key"; Not referencing an index object!
			
			for dbkey in DBKEYS:
				if dbkey in self.contents:
					self.Stream.seek(self.contents[dbkey]["offset"] + self.bodystart, OS.SEEK_SET)
					header  = self.Stream.read(32)
					size    = int.from_bytes(self.Stream.read(4), "little") # Total filesize
					xcctype = int.from_bytes(self.Stream.read(4), "little") # 0 for LMD, 2 for XIF
					version = int.from_bytes(self.Stream.read(4), "little") # Always zero
					mixtype = int.from_bytes(self.Stream.read(4), "little")
					
					if header != XCC_ID or size != self.contents[dbkey]["size"]:
						raise MixError("Invalid database")
					elif mixtype > 6:
						raise MixError("Unsupported MIX type")
					else:
						if mixtype > TYPE_TS: mixtype = TYPE_TS
						
					namecount = int.from_bytes(self.Stream.read(4), "little")
					mixdb     = self.Stream.read(self.contents[dbkey]["size"] - 52).split(b"\x00")
					del(mixdb[-1])
					
					if len(mixdb) != namecount:
						raise MixError("Invalid database")
						
					self.mixtype = mixtype
					for name in mixdb:
						name = name.decode(ENCODING, "replace")
						key = genkey(name, self.mixtype)
						if key in self.contents:
							self.contents[key]["name"] = name
							self.names[name] = key
							
					# Remove MIX Database from index after reading
					self.index.remove(self.contents[dbkey])
					del(self.contents[dbkey])
					break
				
					
		
		
	# Get a file out of the MIX
	def get_file(name, start=0, bytes=-1):
		# Negative start counts bytes from the end
		pass
		
	# Get the index position of a file
	def get_inode(self, key):
		if isinstance(key, str):
			key = self.get_key(key)
			
		return self.index.index(self.contents[key]) if key in self.contents else None
		
	# Get the key for a filename
	def get_key(self, name):
		if name in self.names:
			return self.names[name]
		else:
			key = genkey(name, self.mixtype)
			
			# Add name to index if file exists and does not collide
			if key in self.contents and self.contents[key]["name"] is None:
				self.contents[key]["name"] = name
				self.names[name] = key
				
			return key
			
	# Rename a file in the MIX
	def rename(old, new):
		# This implicitly calls self.get_key()
		inode = self.get_inode(old)
		
		if inode is None:
			raise MixError("File not found")
			
		self.set_name(inode, new)
		
		# Return the most useful information
		return inode
			
	# Set a new name for file at given index
	def set_name(inode, new):
		if isinstance(new, str):
			newname = new
			# If an unknown file "newname" already exists, this will result in the name being added
			new = self.get_key(new)
		else:
			newname = None
			
		# Every key representing "local mix database.dat" is considered reserved
		if new in DBKEYS: raise MixError("Invalid filename")
			
		old     = self.index[inode]["key"]
		oldname = self.index[inode]["name"]
		namechange = True
			
		# If old and new keys differ, we need to check for collisions and update the key
		if old != new:
			if new in self.contents:
				raise MixError("File exists")
				
			# As there was no collision, update the key
			self.index[inode]["key"] = new
			del(self.contents[old])
			self.contents[new] = self.index[inode]
			
			# As key has changed we set a new name, even if it's None (user gave key as new)
			self.index[inode]["name"] = newname
		elif newname is not None and newname != oldname:
			# If old and new keys are the same, set newname only if not None
			self.index[inode]["name"] = newname
		else:
			# This means nothing has changed
			namechange = False
			
		# Update names dict only if name has changed
		if namechange:
			if oldname in self.names: del(this.names[oldname])
			self.names[newname] = new
		
		# Return the most useful information
		return oldname or old
		
		
	# Write current index to MIX
	def write_index():
		if self.Stream.writable():
			# Sort index and write
			pass
		else:
			# Raise warning
			pass
		
	# Returns a AbstractIO instance
	def open(self, file):
		if file:
			pass
			
		# TODO: Check if valid
		return AbstractIO.AbstractIO(self, self.contents["key"]["offset"], self.contents["key"]["size"])
		
	# Moves content out of the way
	def move_away(self, key):
		# Write new content to holes if at least 4M free
		# Move content to holes if big enough
		# Leave at least 1M for index, move away first file when file is added
		# If running out of space while writing content, check if current or 
		pass
		
	# Return if MIX is TD, RA or TS
	def get_type(self):
		return self.mixtype
		
	# Change MIX type only if every file has a name
	def set_type(self):
		if len(self.names) < len(self.index):
			messagebox("Can't set type without knowledge of all names")
			# TODO: raise a warning instead; show message in mixtool
		return self.mixtype
		
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
def genkey(name, mixtype):
	name   = name.upper()
	name   = name.replace("/", "\\\\")
	name   = name.encode(ENCODING, "replace")
	length = len(name)
	
	if mixtype >= TYPE_TS:
		# Compute key for TS MIXes
		a = length & ~3
		if length & 3:
			name += bytes((length - a,))
			name += bytes((name[a],)) * (3 - (length & 3))
		return BinASCII.crc32(name)
	else:
		# Compute key for TD/RA MIXes
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
