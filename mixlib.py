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
TYPE_RG  = 3

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
		filesize = self.Stream.seek(0, OS.SEEK_END)

		if filesize < 4:
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
				filecount = int.from_bytes(self.Stream.read(2), BYTEORDER)
		else:
			# Maybe it's a TD MIX
			self.mixtype = TYPE_TD
			self.has_checksum = False
			self.is_encrypted = False

			# Get header Data for TD
			filecount = firstbytes

		# From here it's the same for every unencrypted MIX
		if not self.is_encrypted:
			bodysize    = int.from_bytes(self.Stream.read(4), BYTEORDER)
			indexoffset = self.Stream.tell()
			indexsize   = filecount * 12
			bodyoffset  = indexoffset + indexsize

			# Check if data is sane
			if filesize - bodyoffset != bodysize:
				messagebox(filesize - bodyoffset)
				messagebox(bodysize)
				raise MixError("Incorrect filesize or invalid header")

			# OK, time to read the index
			index = {}
			for i in range(0, filecount):
				key    = int.from_bytes(self.Stream.read(4), BYTEORDER)
				offset = int.from_bytes(self.Stream.read(4), BYTEORDER) + bodyoffset
				size   = int.from_bytes(self.Stream.read(4), BYTEORDER)

				if offset + size > filesize:
					raise MixError("Content " + hex(key) + " out of range")

				index[key] = {"offset": offset, "size": size, "alloc": size, "name": hex(key)}

			if len(index) != filecount:
				raise MixError("Duplicate key")

		# Now read the names
		for dbkey in DBKEYS:
			if dbkey in index:
				self.Stream.seek(index[dbkey]["offset"], OS.SEEK_SET)
				header = self.Stream.read(32)

				if header != XCC_ID: continue

				dbsize  = int.from_bytes(self.Stream.read(4), BYTEORDER) # Total filesize
				xcctype = int.from_bytes(self.Stream.read(4), BYTEORDER) # 0 for LMD, 2 for XIF
				version = int.from_bytes(self.Stream.read(4), BYTEORDER) # Always zero
				mixtype = int.from_bytes(self.Stream.read(4), BYTEORDER) # XCC Game ID

				if dbsize != index[dbkey]["size"]:
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
				del index[dbkey]
				
				# Populate names dict
				namecount = 0
				for name in namelist:
					name = name.decode(ENCODING, "ignore")
					key = genkey(name, self.mixtype)
					if key in index:
						index[key]["name"] = name
						namecount += 1

				# XCC sometimes puts two Databases in a file by mistake,
				# so if no names were found, give it another try
				if namecount != 0: break

		# Create a list of all contents
		contents = list(index.values())

		# Calculate alloc values
		# This is the size up to wich a file may grow without needing a move
		contents.sort(key=lambda inode: inode["offset"])
		for i in range(0, len(contents) - 1):
			contents[i]["alloc"] = contents[i+1]["offset"] - contents[i]["offset"]
			
		# Export the final index
		self.index = index
		self.contents = contents
		
	# Write index on close if writable
	def __del__(self):
		return # Disabled in Alpha
		if self.Stream.writable():
			self.write_index()

	# Central file-finding method (like stat)
	# Also used to add missing names to the index
	def get_inode(self, name):
		key = self.get_key(name)
		inode = self.index.get(key)
		
		if inode is not None and inode["name"][:2] in ("0x, 0X"):
				inode["name"] = name
				
		return inode
		
	# Get key for any _valid_ name
	def get_key(self, name):
		if not name:
			raise MixNameError("Must not be empty")
			
		try:
			if name[:2] in ("0x", "0X"):
				key = int(name, 16)
			else:
				key = genkey(name, self.mixtype)
		except ValueError:
			raise MixNameError("Invalid filename")
			
		return key

	# Rename a file in the MIX
	def rename(self, old, new):
		oldkey = self.get_key(old)
		inode = self.index.get(old)
		
		if inode is None:
			raise MixError("File not found")
		
		if inode["name"][:2] in ("0x, 0X"):
				inode["name"] = old
		
		newkey = self.get_key(new)
		
		if newkey in DBKEYS:
			raise MixNameError("Invalid filename")
			
		existing = self.index.get(newkey)
				
		if existing:
			if existing is inode:
				# This  means "old" and "new" matched the same key.
				if new[:2] not in ("0x", "0X"):
					inode["name"] = new
				return inode["name"]
			else:
				# In this case a different file by name "new" already exists
				raise MixError("File exists")
			
		# Now rename the file
		del self.index[oldkey]
		inode["name"] = new
		self.index[newkey] = inode
		
		return new
		
	# Change MIX type
	def convert(self, newtype):
		if newtype < TYPE_TD or newtype > TYPE_TS + 3:
			raise MixError("Unsupported MIX type")
		elif newtype > TYPE_TS:
			newtype = TYPE_TS

		if (newtype >= TYPE_TS and self.mixtype < TYPE_TS) or (newtype < TYPE_TS and self.mixtype >= TYPE_TS):
			# This means we have to generate new keys for all names
			newindex = {}
			for inode in self.contents:
				if inode["name"][:2] in ("0x", "0X"):
					raise MixError("Can't convert between TD/RA and TS when names are missing")
					
				newkey = genkey(inode["name"], self.mixtype)
				newindex[newkey] = inode
			self.index = newindex

		# Checksum and Encryption is not supported in TD
		if newtype == TYPE_TD:
			self.has_checksum = False
			self.is_encrypted = False

		self.mixtype = newtype
		return newtype

	# Optimize mix function // Works like defragmentation
	# Reorganizing sorts contents by size with the smallest at that beginning
	def optimize(self, reorganize=False):
		pass

	# Write current header (Flags, Keysource, Index, Database, Checksum) to MIX
	# TODO: Implement context manager
	def write_index(self):
		assert len(self.contents) == len(self.index)
		filecount   = len(self.contents) + 1
		indexoffset = 6 if self.mixtype == TYPE_TD else 10
		indexsize   = filecount * 12
		bodyoffset  = indexoffset + indexsize
		flags       = 0 #self.has_checksum | self.is_encrypted
		
		files = list(self.index.items())
		files.sort(key=lambda i: i[1]["offset"])
		firstfile = files[0][1]
		lastfile = files[-1][1]
		
		# First, anything occupying index space must be moved
		i = 0
		block = BLOCKSIZE
		while firstfile["offset"] < bodyoffset:
			size  = firstfile["size"]
			full  = int(size / block)
			rest  = size % block
			
			rpos = firstfile["offset"]
			wpos = lastfile["offset"] + lastfile["alloc"]
			
			firstfile["offset"] = wpos
			firstfile["alloc"] = size
			
			if full:
				buffer = bytearray(block)
				for j in range(0, full):
					self.Stream.seek(rpos, OS.SEEK_SET)
					rpos += self.Stream.readinto(buffer)
					self.Stream.seek(wpos, OS.SEEK_SET)
					wpos += self.Stream.write(buffer)
				
			if rest:
				self.Stream.seek(rpos, OS.SEEK_SET)
				buffer = self.Stream.read(rest)
				self.Stream.seek(wpos, OS.SEEK_SET)
				self.Stream.write(buffer)
				
			del buffer
				
			i += 1
			lastfile = firstfile
			firstfile = files[i][1]
		if i:
			files.sort(key=lambda i: i[1]["offset"])
			
		# Write names
		dbsize = 52
		namecount = 1
		dboffset = lastfile["offset"] + lastfile["alloc"]
		
		self.Stream.seek(dboffset, OS.SEEK_SET)
		self.Stream.write(bytes(dbsize))
		for key, inode in files:
			if inode["name"][:2] not in ("0x, 0X"):
				dbsize += self.Stream.write(inode["name"].encode(ENCODING, "strict"))
				dbsize += self.Stream.write(bytes(1))
				namecount += 1
		self.Stream.write(b"local mix database.dat\x00")
		self.Stream.truncate()
		
		# Write database header
		self.Stream.seek(dboffset, OS.SEEK_SET)
		messagebox(dboffset)
		messagebox(self.Stream.tell())
		self.Stream.write(XCC_ID)
		self.Stream.write(dbsize.to_bytes(4, BYTEORDER))
		self.Stream.write(bytes(8))
		self.Stream.write(self.mixtype.to_bytes(4, BYTEORDER))
		self.Stream.write(namecount.to_bytes(4, BYTEORDER))
			
		# Write index
		bodysize = 0
		dbkey = DBKEYS[1] if self.mixtype == TYPE_TS else DBKEYS[0]
		
		self.Stream.seek(bodyoffset, OS.SEEK_SET)
		for key, inode in files:
			self.Stream.write(key.to_bytes(4, BYTEORDER))
			self.Stream.write((inode["offset"] - bodyoffset).to_bytes(4, BYTEORDER))
			self.Stream.write(inode["size"].to_bytes(4, BYTEORDER))
			bodysize += inode["alloc"]
		self.Stream.write(dbkey.to_bytes(4, BYTEORDER))
		self.Stream.write((dboffset - bodyoffset).to_bytes(4, BYTEORDER))
		self.Stream.write(dbsize.to_bytes(4, BYTEORDER))
		
		# Write MIX header
		self.Stream.seek(0, OS.SEEK_SET)
		if self.mixtype != TYPE_TD:
			self.Stream.write(bytes(2))
			self.Stream.write(flags.to_bytes(2, BYTEORDER))
		self.Stream.write(filecount.to_bytes(2, BYTEORDER))
		self.Stream.write(bodysize.to_bytes(4, BYTEORDER))
				
			
	# Return if MIX is TD, RA or TS
	def get_type(self):
		return ("TD", "RA", "TS")[self.mixtype]
		
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
		key = self.get_key(name)
		inode = self.index.get(key)
		
		if inode is not None:
			if inode["name"][:2] in ("0x, 0X"):
				inode["name"] = name
			raise MixError("File exists")
			
		# TODO: Add code to find better position
		
		self.contents.sort(key=lambda inode: inode["offset"])
		offset = self.contents[-1]["offset"] + self.contents[-1]["alloc"]
		size = OS.stat(source).st_size
		
		inode = {"name": name, "offset": offset, "size": size, "alloc": size}
		self.index[key] = inode
		self.contents.append(inode)
		
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
				
		return inode

	# Opens a file inside the MIX using MixIO
	# Works like the build-in open function
	def open(self, name, mode="r", buffering=4194304, encoding=None, errors=None):
		inode = self.get_inode()
		self.files_open.append(id(inode))


# MixIO instaces are used to work with contained files as if they were real
class MixIO(IO.BufferedIOBase):
	pass


class MixError(Exception):
	# TODO: For internal errors
	pass
	
class MixNameError(ValueError):
	# TODO: For invalid name errors
	pass
	

# Create MIX-Identifier from filename
# Thanks to Olaf van der Spek for providing these functions
def genkey(name, mixtype):
	name = name.encode(ENCODING, "strict")
	name = name.upper()
	len_ = len(name)

	if mixtype == TYPE_TS:
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
