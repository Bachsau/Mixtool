#!/usr/bin/python3
# coding=utf8

import binascii   as BinASCII
import os         as OS
import io         as IO

from mixtool_gtk  import messagebox

# MixLib implements a file-in-file type class that can be used by AbstractIO.
# To AbstractIO it is what the standard OS module is to standard IO.
# MixLib and AbstractIO work together to build an in-python-file-system and stream API.

# Constants
FLAG_CHECKSUM  = 1
FLAG_ENCRYPTED = 2

TYPE_TD  = 0
TYPE_RA  = 1
TYPE_TS  = 2

DBKEYS   = 1422054725, 913179935
KEYFILE  = 1983676893

XCC_ID    = b"XCC by Olaf van der Spek\x1a\x04\x17\x27\x10\x19\x80\x00"
ENCODING  = "cp1252"
BYTEORDER = "little"


# Instance representing a single MIX file
# Think of this as a file system driver
class MixFile:
	# Constructor opens MIX file
	# Must work on a BufferedIO stream
	def __init__(self, stream, new=False, mixtype=None):
		self.Stream = stream
		self.filesize = self.Stream.seek(0, OS.SEEK_END)
		
		if self.filesize < 4:
			raise MixError("File too small")
		
		# A list to handle descriptors of files opened inside the MIX
		self.files_open = []
		
		# First two bytes are zero for RA/TS and the number of files for TD
		self.Stream.seek(0, OS.SEEK_SET)
		firstbytes = int.from_bytes(self.Stream.read(2), BYTEORDER)
		if firstbytes == 0:
			# It seems we have a RA/TS MIX so decode the flags
			flags = int.from_bytes(self.Stream.read(2), BYTEORDER)
			self.has_checksum = flags & FLAG_CHECKSUM == FLAG_CHECKSUM
			self.is_encrypted = flags & FLAG_ENCRYPTED == FLAG_ENCRYPTED
			
			# Encrypted TS MIXes have a key.ini we can check for later,
			# so at this point assume TYPE_TS only if unencrypted
			self.mixtype = TYPE_RA if self.is_encrypted else TYPE_TS
			
			# Get header data for RA/TS
			if self.is_encrypted:
				# OK, we have to deal with this first
				raise MixError("MIX is encrypted. Decrypting MIX headers ist not yet supported.")
			else:
				# RA/TS MIXes hold their filecount after the flags,
				# whilst for TD MIXes their first two bytes are the filecount.
				self.filecount = int.from_bytes(self.Stream.read(2), BYTEORDER)
		else:
			# Maybe it's a TD MIX
			self.mixtype = TYPE_TD
			self.has_checksum = False
			self.is_encrypted = False
			
			# Get header Data for TD
			self.filecount = firstbytes
			
		# From here it's the same for every unencrypted MIX
		if not self.is_encrypted:
			self.contentsize  = int.from_bytes(self.Stream.read(4), BYTEORDER)
			self.indexstart   = self.Stream.tell()
			self.indexsize    = self.filecount * 12
			self.contentstart = self.indexstart + self.indexsize
			
			# Check if data is sane
			if self.filesize - self.contentstart != self.contentsize:
				raise MixError("Incorrect filesize or invalid header")
				
			# OK, time to read the index
			minoffset = None
			self.index = []
			self.contents = {}
			for i in range(0, self.filecount):
				key    = int.from_bytes(self.Stream.read(4), BYTEORDER)
				offset = int.from_bytes(self.Stream.read(4), BYTEORDER) + self.contentstart
				size   = int.from_bytes(self.Stream.read(4), BYTEORDER)
				
				if offset + size > self.filesize:
					raise MixError("Content " + hex(key) + " out of range")
					
				if minoffset is None or offset < minoffset: minoffset = offset
				
				self.index.append({"offset": offset, "size": size, "alloc": size, "key": key, "name": None})
				self.contents[key] = self.index[i]
				
			if len(self.index) != len(self.contents):
				raise MixError("Duplicate key")
				
			# Now read the Local MIX Database
			self.names = {} # Pairs of "Name: Key"; Not referencing an index row!
			
			for dbkey in DBKEYS:
				if dbkey in self.contents:
					self.Stream.seek(self.contents[dbkey]["offset"], OS.SEEK_SET)
					header = self.Stream.read(32)
					
					if header != XCC_ID: continue
					
					size    = int.from_bytes(self.Stream.read(4), BYTEORDER) # Total filesize
					xcctype = int.from_bytes(self.Stream.read(4), BYTEORDER) # 0 for LMD, 2 for XIF
					version = int.from_bytes(self.Stream.read(4), BYTEORDER) # Always zero
					mixtype = int.from_bytes(self.Stream.read(4), BYTEORDER)
					
					if size != self.contents[dbkey]["size"]:
						raise MixError("Invalid database")
					
					if mixtype > TYPE_TS + 3:
						raise MixError("Unsupported MIX type")
					elif mixtype > TYPE_TS:
						mixtype = TYPE_TS
						
					namecount = int.from_bytes(self.Stream.read(4), BYTEORDER)
					bodysize  = self.contents[dbkey]["size"] - 53
					mixdb     = self.Stream.read(bodysize).split(b"\x00") if bodysize > 0 else []
					
					if len(mixdb) != namecount:
						raise MixError("Invalid database")
						
					self.mixtype = mixtype
					for name in mixdb:
						name = name.decode(ENCODING, "replace")
						key = genkey(name, self.mixtype)
						if key in self.contents and key != dbkey:
							self.contents[key]["name"] = name
							self.names[name] = key
							
					# Remove MIX Database from index after reading
					self.index.remove(self.contents[dbkey])
					del(self.contents[dbkey])
					self.filecount -= 1
					
					# XCC sometimes puts two Databases in a file by mistake,
					# so if no names were found, give it another try
					if len(self.names) != 0: break
					
			# Sort the index by offset
			self.index.sort(key=lambda i: i["offset"])
			
			# Calculate alloc values
			# This is the size up to wich a file may grow without needing a move
			for i in range(0, len(self.index) - 1):
				self.index[i]["alloc"] = self.index[i+1]["offset"] - self.index[i]["offset"]				
		
	# Destructor writes index to file if not read only
	def __del__(self):
		if self.Stream.writable(): self.write_header()
	
	# Get a file out of the MIX
	def get_file(self, key):
		if not isinstance(key, int):
			key = self.get_key(key)
		
		self.Stream.seek(self.contents[key]["offset"], OS.SEEK_SET)
		return self.Stream.read(self.contents[key]["size"])
		
	# Get the key for a filename
	# Also used to add missing names to the index
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
			
	# Extract a file to the local filesystem
	def extract(self, key, dest):
		if not isinstance(key, int):
			key = self.get_key(key)
			
		with open(dest, "wb") as OutFile:
			# TODO: Do not place whole file in memory
			OutFile.write(self.get_file(key))
			
	# Rename a file in the MIX
	def rename(self, old, new):
		if not isinstance(old, int):
			old = self.get_key(key)
			
		if not isinstance(new, int):
			newname = new
			# If an unknown file "newname" already exists, this will result in the name being added
			new = self.get_key(new)
		else:
			newname = None
			
		# Every key representing a Local MIX Database is considered reserved
		if new in DBKEYS: raise MixError("Invalid filename")
		
		inode   = self.contents[old]
		oldname = self.contents[old]["name"]
		namechange = False
			
		# If old and new keys differ, we need to check for collisions and update the key
		if old != new:
			if new in self.contents:
				raise MixError("File exists")
				
			# As there was no collision, update the key
			inode["key"] = new
			del(self.contents[old])
			self.contents[new] = inode
			
			# Key has changed, so set a new name, even if it's None (user gave key as new)
			inode["name"] = newname
			namechange = True
			
		# If old and new keys are the same, set newname only if not None
		elif newname is not None and newname != oldname:
			inode["name"] = newname
			namechange = True
			
		# Update names dict only if name has changed
		if namechange:
			if oldname in self.names: del(self.names[oldname])
			self.names[newname] = new
		
		# Return new key. Maybe useful if name was given.
		return new
		
	# Set new name for a given inode number
	def set_name(self, nodenum, new):
		old     = self.index[nodenum]["key"]
		oldname = self.index[nodenum]["name"]
		rename(old, new)
		
		return oldname or old
		
	# Write current header (Flags, Keysource, Index, Database, Checksum) to MIX
	# TODO: Implement context manager
	def write_header():
		pass
			
	# Opens a file inside the MIX using AbstractIO
	# by calling AbstractIO.open much like IO.open
	# This is a public high-level method, not the "opener",
	# It does not implement a standard libs function.
	def open(self, name, mode="r", buffering=4194304, encoding=None, errors=None):
		return AbstractIO.open(name, self, mode, buffering, encoding, errors, None, True, self._opener)
		
	# Implements OS.open() with "OS" being _this_ MIX
	# http://docs.python.org/3/library/os.html#os.open
	# Serves as the opener to AbstractIO.open
	def _opener(self, key, flags, mode=0o777):
		if not isinstance(key, int):
			key = self.get_key(key)
			
		fd = len(self.files_open)
		self.files_open.append(self.contents[key])
		return fd
		
	# Moves content out of the way
	def move_away(self, key):
		# Write new content to holes if at least 4M free
		# Move content to holes if big enough
		# Leave at least 1M for index, move away first file when file is added
		# If running out of space while writing content, check if current or 
		pass
		
	# Return if MIX is TD, RA or TS
	def get_type(self):
		return ("TD", "RA", "TS")[self.mixtype]
		
	# Change MIX type
	def convert(self, newtype):
		if newtype < TYPE_TD or newtype > TYPE_TS + 3:
			raise MixError("Unsupported MIX type")
		elif newtype > TYPE_TS:
			newtype = TYPE_TS
		
		if (newtype >= TYPE_TS and self.mixtype < TYPE_TS) or (newtype < TYPE_TS and self.mixtype >= TYPE_TS):
			# This means we have to convert all names
			if len(self.names) < len(self.index):
				raise MixError("Can't convert between TD/RA and TS when names are missing")
				
				newkeys = {}
				# Generate a new key for every name
				for inode in self.index:
					key = genkey(inode["name"], newtype)
					newkeys[key] = inode
			
				if len(newkeys) != len(self.index):
					raise MixError("Key collision")
				else:
					# Update keys in index and names dict
					for key, inode in items(newkeys):
						inode["key"] = key
						self.names[inode["name"]] = key
					self.contents = newkeys
					
		# Checksum and Encryption is not supported in TD
		if newtype < TYPE_RA:
			self.has_checksum = False
			self.is_encrypted = False
			
		self.mixtype = newtype
		return self.mixtype
		
	# Compact mix function // Works like defragmentation
	# Reorganizing orders contents by size with the smallest at that beginning
	def compact(self, reorganize=False):
		pass
		
# MixIO instaces are used to work with contained files as if they were real
class MixIO(IO.BufferedIOBase):
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
