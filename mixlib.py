#!/usr/bin/python3
# coding=utf8

# Mixtool – An editor for Westwood Studios’ MIX files
# Copyright (C) 2015 Bachsau
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import os         as OS
import io         as IO
import binascii   as BinASCII

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

DBKEYS    = 1422054725, 913179935
KEYFILE   = 1983676893
BLOCKSIZE = 4194304

XCC_ID    = b"XCC by Olaf van der Spek\x1a\x04\x17\x27\x10\x19\x80\x00"
ENCODING  = "cp1252"
BYTEORDER = "little"


# Instance representing a single MIX file
# Think of this as a file system driver
class MixFile(object):
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
		if not firstbytes:
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
			rawindex = {}
			for i in range(0, self.filecount):
				key    = int.from_bytes(self.Stream.read(4), BYTEORDER)
				offset = int.from_bytes(self.Stream.read(4), BYTEORDER) + self.contentstart
				size   = int.from_bytes(self.Stream.read(4), BYTEORDER)

				if offset + size > self.filesize:
					raise MixError("Content " + hex(key) + " out of range")

				rawindex[key] = (offset, size)

			if len(rawindex) != self.filecount:
				raise MixError("Duplicate key")

		# Now read the names
		names = {}
		for dbkey in DBKEYS:
			if dbkey in rawindex:
				self.Stream.seek(rawindex[dbkey][0], OS.SEEK_SET)
				header = self.Stream.read(32)

				if header != XCC_ID: continue

				dbsize  = int.from_bytes(self.Stream.read(4), BYTEORDER) # Total filesize
				xcctype = int.from_bytes(self.Stream.read(4), BYTEORDER) # 0 for LMD, 2 for XIF
				version = int.from_bytes(self.Stream.read(4), BYTEORDER) # Always zero
				mixtype = int.from_bytes(self.Stream.read(4), BYTEORDER) # XCC Game ID

				if dbsize != rawindex[dbkey][1]:
					raise MixError("Invalid database")

				if mixtype > TYPE_TS + 3:
					raise MixError("Unsupported MIX type")
				elif mixtype > TYPE_TS:
					mixtype = TYPE_TS

				self.mixtype = mixtype

				namecount = int.from_bytes(self.Stream.read(4), BYTEORDER)
				bodysize  = dbsize - 53 # Size - header - last byte
				namelist  = self.Stream.read(bodysize).split(b"\x00") if bodysize > 0 else []

				if len(namelist) != namecount:
					raise MixError("Invalid database")

				# Remove Database from index
				del rawindex[dbkey]
				self.filecount -= 1
				
				# Populate names dict
				for name in namelist:
					name = name.decode(ENCODING, "ignore")
					key = genkey(name, self.mixtype)
					if key in rawindex:
						names[key] = name

				# XCC sometimes puts two Databases in a file by mistake,
				# so if no names were found, give it another try
				if len(names) != 0: break

		# Create a dict and list of all contents
		index = {}
		contents = []
		for key, values in rawindex.items():
			name = names.get(key, hex(key))
			inode = {"name": name, "offset": values[0], "size": values[1], "alloc": values[1]}
			index[name] = inode
			contents.append(inode)

		# Calculate alloc values
		# This is the size up to wich a file may grow without needing a move
		contents.sort(key=lambda i: i["offset"])
		for i in range(0, len(contents) - 1):
			contents[i]["alloc"] = contents[i+1]["offset"] - contents[i]["offset"]
			
		# Export the final index
		self.index = index
		self.contents = contents


	# Central file-finding method (like stat)
	# Also used to add missing names to the index
	def get_inode(self, name):
		inode = self.index.get(name)
		
		# Nothing found, so try a key
		if inode is None and name[0:2] not in ("0x", "0X"):
			try:
				key = genkey(name, self.mixtype)
			except ValueError:
				pass
			else:
				inode = self.index.get(hex(key))
				
				# Reset name if file exists
				if inode is not None:
					del self.index[inode["name"]]
					inode["name"] = name
					self.index[name] = inode

		return inode

	# Get a file out of the MIX
	def get_file(self, name):
		inode = self.get_inode(name)
		
		if inode is None:
			raise MixError("File not found")

		self.Stream.seek(inode["offset"], OS.SEEK_SET)
		return self.Stream.read(inode["size"])

	# Extract a file to local filesystem
	def extract(self, name, dest):
		inode = self.get_inode(name)
		
		if inode is None:
			raise MixError("File not found")
		
		block = BLOCKSIZE
		size  = inode["size"]
		full  = int(size / block)
		rest  = size % block
		
		assert not OS.path.isfile(dest)
		
		self.Stream.seek(inode["offset"], OS.SEEK_SET)
		with open(dest, "wb") as OutFile:
			for i in range(0, full):
				buffer = self.Stream.read(block)
				OutFile.write(buffer)
			if rest:
				buffer = self.Stream.read(rest)
				OutFile.write(buffer)
			
	# Insert a file from local filesystem
	def insert(self, name, source):
		if not checkname(name, self.mixtype):
			raise MixError("Invalid Filename")
			
		if self.get_inode(name):
			raise MixError("File exists")
			
		# TODO: Add for loop to find better position
		
		self.contents.sort(key=lambda i: i["offset"])
		offset = self.contents[-1]["offset"] + self.contents[-1]["size"]
		size = OS.stat(source).st_size
		
		block = BLOCKSIZE
		full  = int(size / block)
		rest  = size % block
		
		self.Stream.seek(offset, OS.SEEK_SET)
		with open(source, "rb") as InFile:
			for i in range(0, full):
				buffer = InFile.read(block)
				self.Stream.write(buffer)
			if rest:
				buffer = InFile.read(block)
				self.Stream.write(buffer)
			
		inode = {"name": name.lower(), "offset": offset, "size": size, "alloc": size}
		self.index[name] = inode
		self.contents.append(inode)
				
		return inode

	# Rename a file in the MIX
	def rename(self, old, new):
		inode = self.get_inode(old)
		
		if inode is None:
			raise MixError("File not found")
			
		if not checkname(new, self.mixtype):
			raise MixError("Invalid filename")
			
		new = new.lower()
		newnode = self.get_inode(new)
		
		if newnode is not None:
			if inode is newnode:
				# This either means "old" and "new" were equal or "new" matched the key
				# of previously un-named old, which caused get_inode() to reset its name
				return new
			else:
				# In this case a different file by name "new" already exists
				raise MixError("File exists")
			
		# Now rename the file
		del self.index[inode["name"]]
		inode["name"] = new
		self.index[new] = inode
		
		return new

	# Write current header (Flags, Keysource, Index, Database, Checksum) to MIX
	# TODO: Implement context manager
	def write_index():
		if self.Stream.writable():
			keys = set(DBKEYS) # Collects generated keys to detect collisions
			self.index.sort(key=lambda i: i["offset"])

	# Opens a file inside the MIX using MixIO
	# Works like the build-in open function
	def open(self, name, mode="r", buffering=4194304, encoding=None, errors=None):
		inode = self.get_inode()
		self.files_open.append(id(inode))

	# Moves content out of the way
	def move_away(self, name):
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
			for inode in self.contents:
				if inode["name"][0:2] in ("0x", "0X"):
					raise MixError("Can't convert between TD/RA and TS when names are missing")

		# Checksum and Encryption is not supported in TD
		if newtype < TYPE_RA:
			self.has_checksum = False
			self.is_encrypted = False

		self.mixtype = newtype
		return self.mixtype

	# Optimize mix function // Works like defragmentation
	# Reorganizing sorts contents by size with the smallest at that beginning
	def optimize(self, reorganize=False):
		pass

# MixIO instaces are used to work with contained files as if they were real
class MixIO(IO.BufferedIOBase):
	pass


class MixError(Exception):
	# TODO: Create real error class
	pass
	
# Check if something is a valid name
def checkname(name, mixtype):
	if len(name) == 0 or len(name) > 255:
		return False
		
	if name[0:2] in ("0x", "0X"):
		return False
	
	try:
		key = genkey(name, mixtype)
	except (TypeError, ValueError):
		return False
	else:
		if key in DBKEYS:
			return False
			
	return True

# Create MIX-Identifier from filename
# Thanks to Olaf van der Spek for providing these functions
def genkey(name, mixtype):
	name = name.encode(ENCODING, "strict")
	name = name.upper()
	len_ = len(name)

	if mixtype >= TYPE_TS:
		# Compute key for TS MIXes
		a = len_ & ~3
		if len_ & 3:
			name += bytes((len_ - a,))
			name += bytes((name[a],)) * (3 - (len_ & 3))
		return BinASCII.crc32(name)
	else:
		# Compute key for TD/RA MIXes
		i   = 0
		key = 0
		while i < len_:
			a = 0
			for j in range(0, 4):
				a >>= 8
				if i < len_:
					a |= (name[i] << 24)
					i += 1
			key = (key << 1 | key >> 31) + a & 4294967295
		return key
