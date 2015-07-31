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

"""Routines to access MIX files"""
import os         as OS
import io         as IO
import binascii   as BinASCII

from mixtool_gtk  import messagebox

# Constants
FLAG_CHECKSUM  = 1
FLAG_ENCRYPTED = 2

TYPE_TD  = 0
TYPE_RA  = 1
TYPE_TS  = 2

DBKEYS    = 1422054725, 913179935
KEYFILE   = 1983676893
BLOCKSIZE = 2097152

XCC_ID = b"XCC by Olaf van der Spek\x1a\x04\x17\x27\x10\x19\x80\x00"


# Instance representing a single MIX file
# Think of this as a file system driver
class MixFile(object):
	"Manage MIX files, one file per instance."
	__slots__ = "Stream", "files_open", "index", "contents", "mixtype", "has_checksum", "is_encrypted"
	
	# Constructor parses MIX file
	def __init__(self, stream, new=None):
		"""
		Parse a MIX from 'stream', which must be a buffered file object.
		
		If 'new' is given, initialize an empty MIX of type 'new' instead.
		MixError ist raised on any parsing errors.
		"""
		self.Stream = stream
		self.files_open = []
		self.index = {}
		self.contents = []
		self.mixtype = 0
		self.has_checksum = False
		self.is_encrypted = False
		
		# For new files, initialize mixtype and return
		if new is not None:
			if new < TYPE_TD or new > TYPE_TS:
				raise MixError("Unsupported MIX type")
			self.mixtype = int(new)
			return
		
		filesize = self.Stream.seek(0, OS.SEEK_END)
		if filesize < 4:
			raise MixError("File too small")

		# First two bytes are zero for RA/TS and the number of files for TD
		self.Stream.seek(0)
		firstbytes = int.from_bytes(self.Stream.read(2), "little")
		if not firstbytes:
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
				raise MixError("MIX is encrypted, which ist not yet supported.")
			else:
				# RA/TS MIXes hold their filecount after the flags,
				# whilst for TD MIXes their first two bytes are the filecount.
				filecount = int.from_bytes(self.Stream.read(2), "little")
		else:
			# Maybe it's a TD MIX
			self.mixtype = TYPE_TD

			# Get header Data for TD
			filecount = firstbytes

		# From here it's the same for every unencrypted MIX
		if not self.is_encrypted:
			bodysize    = int.from_bytes(self.Stream.read(4), "little")
			indexoffset = self.Stream.tell()
			indexsize   = filecount * 12
			bodyoffset  = indexoffset + indexsize

			# Check if data is sane
			if filesize - bodyoffset != bodysize:
				raise MixError("Incorrect filesize or invalid header")

			# OK, time to read the index
			for i in range(0, filecount):
				key    = int.from_bytes(self.Stream.read(4), "little")
				offset = int.from_bytes(self.Stream.read(4), "little") + bodyoffset
				size   = int.from_bytes(self.Stream.read(4), "little")

				if offset + size > filesize:
					raise MixError("Content " + hex(key) + " out of range")

				self.index[key] = mixnode(hex(key), offset, size, size)

			if len(self.index) != filecount:
				raise MixError("Duplicate key")

		# Now read the names
		for dbkey in DBKEYS:
			if dbkey in self.index:
				self.Stream.seek(self.index[dbkey].offset)
				header = self.Stream.read(32)

				if header != XCC_ID: continue

				dbsize  = int.from_bytes(self.Stream.read(4), "little") # Total filesize
				xcctype = int.from_bytes(self.Stream.read(4), "little") # 0 for LMD, 2 for XIF
				version = int.from_bytes(self.Stream.read(4), "little") # Always zero
				mixtype = int.from_bytes(self.Stream.read(4), "little") # XCC Game ID

				if dbsize != self.index[dbkey].size:
					raise MixError("Invalid database")

				if mixtype > TYPE_TS + 3:
					raise MixError("Unsupported MIX type")
				elif mixtype > TYPE_TS:
					mixtype = TYPE_TS

				self.mixtype = mixtype

				namecount = int.from_bytes(self.Stream.read(4), "little")
				bodysize  = dbsize - 53 # Size - header - last byte
				namelist  = self.Stream.read(bodysize).split(b"\x00") if bodysize > 0 else []

				if len(namelist) != namecount:
					raise MixError("Invalid database")

				# Remove Database from index
				del self.index[dbkey]
				
				# Add names to index
				namecount = 0
				for name in namelist:
					name = name.decode("cp1252", "ignore")
					key = genkey(name, self.mixtype)
					if key in self.index:
						self.index[key].name = name
						namecount += 1

				# XCC sometimes puts two Databases in a file by mistake,
				# so if no names were found, give it another try
				if namecount: break

		# Create a sorted list of all contents
		self.contents = sorted(self.index.values())

		# Calculate alloc values
		# This is the size up to wich a file may grow without needing a move
		for i in range(0, len(self.contents) - 1):
			self.contents[i].alloc = self.contents[i+1].offset - self.contents[i].offset
			
			if self.contents[i].alloc < self.contents[i].size:
				raise MixError("Overlapping file boundaries")

	# Central file-finding method (like stat)
	# Also used to add missing names to the index
	def get_inode(self, name):
		"""
		Return the inode for 'name' or None if not found.
		
		Will save 'name' to the index if missing.
		MixNameError is raised if 'name' is not valid.
		"""
		key = self.get_key(name)
		inode = self.index.get(key)
		
		if inode is not None and inode.name[:2] == "0x":
				inode.name = name
				
		return inode
		
	# Get key for any _valid_ name
	def get_key(self, name):
		"""
		Return the key for 'name', regardless of it being in the mix.
		
		MixNameError is raised if 'name' is not valid.
		"""
		if not name:
			raise MixNameError("Must not be empty")
			
		try:
			if name[:2] == "0x":
				key = int(name, 16)
			else:
				key = genkey(name, self.mixtype)
		except ValueError:
			raise MixNameError("Invalid filename")
			
		return key

	# Rename a file in the MIX
	def rename(self, old, new):
		"""
		Rename a file in the MIX.
		
		MixError is raised if the file is not found or a file named 'new' already exists.
		MixNameError is raised if 'name' is not valid.
		"""
		oldkey = self.get_key(old)
		inode = self.index.get(old)
		
		if inode is None:
			raise MixError("File not found")
		
		if inode.name[:2] == "0x":
				inode.name = old
		
		newkey = self.get_key(new)
		
		if newkey in DBKEYS:
			raise MixNameError("Invalid filename")
			
		existing = self.index.get(newkey)
				
		if existing:
			if existing is inode:
				# This  means "old" and "new" matched the same key.
				if new[:2] != "0x":
					inode.name = new
				return inode.name
			else:
				# In this case a different file by name "new" already exists
				raise MixError("File exists")
			
		# Now rename the file
		del self.index[oldkey]
		inode.name = new
		self.index[newkey] = inode
		
	# Change MIX type
	def convert(self, newtype):
		"""
		Convert MIX to 'newtype'.
	
		When converting between	TD/RA and TS the MIX is not allowed to have missing
		names as they can not be properly converted. MixError is raised in this	case.
		"""
		if newtype < TYPE_TD or newtype > TYPE_TS + 3:
			raise MixError("Unsupported MIX type")
		elif newtype > TYPE_TS:
			newtype = TYPE_TS

		if (newtype >= TYPE_TS and self.mixtype < TYPE_TS)\
		or (newtype < TYPE_TS and self.mixtype >= TYPE_TS):
			# This means we have to generate new keys for all names
			newindex = {}
			for inode in self.contents:
				if inode.name[:2] == "0x":
					raise MixError("Can't convert between TD/RA and TS when names are missing")
					
				newkey = genkey(inode.name, self.mixtype)
				newindex[newkey] = inode
				
			if len(newindex) != len(self.contents):
				raise MixError("Key collision")
				
			self.index = newindex

		# Checksum and Encryption is not supported in TD
		if newtype == TYPE_TD:
			self.has_checksum = False
			self.is_encrypted = False

		self.mixtype = newtype

	# Write current header (Flags, Keysource, Index, Database, Checksum) to MIX
	# TODO: Implement context manager
	def write_index(self, optimize=False):
		"""
		Write current index to file and flush the buffer.
		
		If 'optimize' is given and True, the MIX's contents	will be concatenated
		and overhead removed, so it is ready for distribution.
		"""
		assert len(self.contents) == len(self.index)
		filecount   = len(self.contents) + 1
		indexoffset = 6 if self.mixtype == TYPE_TD else 10
		indexsize   = filecount * 12
		bodyoffset  = indexoffset + indexsize
		flags       = 0
		files       = list(self.index.items())
		block       = BLOCKSIZE

		# First, anything occupying index space must be moved
		files.sort(key=lambda i: i[1].offset)
		firstfile = files[0][1]
		lastfile = files[-1][1]
		i = 0
		while firstfile.offset < bodyoffset:
			size = firstfile.size
			full = size // block
			rest = size % block
			
			rpos = firstfile.offset
			wpos = lastfile.offset + lastfile.alloc
			
			firstfile.offset = wpos
			firstfile.alloc = size
			
			if full:
				buffer = bytearray(block)
				for j in range(0, full):
					self.Stream.seek(rpos)
					rpos += self.Stream.readinto(buffer)
					self.Stream.seek(wpos)
					wpos += self.Stream.write(buffer)
				
			if rest:
				self.Stream.seek(rpos)
				buffer = self.Stream.read(rest)
				self.Stream.seek(wpos)
				self.Stream.write(buffer)
				
			del buffer
			
			i += 1
			lastfile = firstfile
			firstfile = files[i][1]
			
		# TODO: Concatenate files if optimize was requested
		if optimize:
			files.sort(key=lambda i: i[1].offset)
			
		# Write names
		dbsize = 75
		namecount = 1
		dboffset = lastfile.offset + lastfile.alloc
		
		self.Stream.seek(dboffset)
		self.Stream.write(bytes(52))
		for key, inode in files:
			if inode.name[:2] != "0x":
				dbsize += self.Stream.write(inode.name.encode("cp1252", "strict"))
				dbsize += self.Stream.write(b"\x00")
				namecount += 1
		self.Stream.write(b"local mix database.dat\x00")
		self.Stream.truncate()
		
		# Write database header
		self.Stream.seek(dboffset)
		self.Stream.write(XCC_ID)
		self.Stream.write(dbsize.to_bytes(4, "little"))
		self.Stream.write(bytes(8))
		self.Stream.write(self.mixtype.to_bytes(4, "little"))
		self.Stream.write(namecount.to_bytes(4, "little"))
			
		# Write index
		bodysize = firstfile.offset - bodyoffset + dbsize
		dbkey = DBKEYS[1] if self.mixtype == TYPE_TS else DBKEYS[0]
		
		self.Stream.seek(indexoffset)
		for key, inode in files:
			self.Stream.write(key.to_bytes(4, "little"))
			self.Stream.write((inode.offset - bodyoffset).to_bytes(4, "little"))
			self.Stream.write(inode.size.to_bytes(4, "little"))
			bodysize += inode.alloc
			
		self.Stream.write(dbkey.to_bytes(4, "little"))
		self.Stream.write((dboffset - bodyoffset).to_bytes(4, "little"))
		self.Stream.write(dbsize.to_bytes(4, "little"))
		
		# Write MIX header
		self.Stream.seek(0)
		if self.mixtype != TYPE_TD:
			self.Stream.write(bytes(2))
			self.Stream.write(flags.to_bytes(2, "little"))
		self.Stream.write(filecount.to_bytes(2, "little"))
		self.Stream.write(bodysize.to_bytes(4, "little"))
		
		self.Stream.flush()
				
			
	# Return if MIX is TD, RA or TS
	def get_type(self):
		"Return a string describing the MIX type. Will be one of TD, RA, TS."
		return ("TD", "RA", "TS")[self.mixtype]
		
	# Get a file out of the MIX
	def get_file(self, name):
		"""
		Return the contents of 'name' as a single bytes object.
		
		MixError is raised if the file is not found.
		"""
		inode = self.get_inode(name)
		
		if inode is None:
			raise MixError("File not found")

		self.Stream.seek(inode.offset)
		return self.Stream.read(inode.size)
		
	# Remove a file from the MIX
	def delete(self, name):
		"""
		Remove 'name' from the MIX
		
		MixError is raised if the file is not found.
		MixNameError is raised if 'name' is not valid.
		"""
		key = self.get_key(name)
		inode = self.contents.get(key)
		
		if inode is None:
			raise MixError("File not found")
			
		self.contents.sort()
			
		index = self.contents.index(inode)
		self.contents[index-1].alloc += inode.alloc
		del self.contents[index]
		del self.index[key]
			
	# Extract a file to local filesystem
	def extract(self, name, dest):
		"""
		Extract 'name' to 'dest' on the local file system.
		
		Existing files will be overwritten.
		MixError is raised if the file is not found.
		MixNameError is raised if 'name' is not valid.
		"""
		inode = self.get_inode(name)
		
		if inode is None:
			raise MixError("File not found")
		
		block = BLOCKSIZE
		size = inode.size
		full = size // block
		rest = size % block
		
		assert not OS.path.isfile(dest)
		
		self.Stream.seek(inode.offset)
		with IO.open(dest, "wb") as OutFile:
			if full:
				buffer = bytearray(block)
				for i in range(0, full):
					self.Stream.readinto(buffer)
					OutFile.write(buffer)
			if rest:
				buffer = self.Stream.read(rest)
				OutFile.write(buffer)
			
	# Insert a file from local filesystem
	def insert(self, name, source):
		"""
		Insert 'source' from the local file system as 'name' and return its inode.
		
		MixError is raised if a file by that name already exists.
		MixNameError is raised if 'name' is not valid.
		"""
		key = self.get_key(name)
		inode = self.index.get(key)
		
		if inode is not None:
			if inode.name[:2] == "0x":
				inode.name = name
			raise MixError("File exists")
			
		# TODO: Add code to find better position
		
		self.contents.sort()
		offset = self.contents[-1].offset + self.contents[-1].alloc
		size = OS.stat(source).st_size
		
		inode = mixnode(name, offset, size, size)
		self.index[key] = inode
		self.contents.append(inode)
		
		block = BLOCKSIZE
		full = size // block
		rest = size % block
		
		self.Stream.seek(offset)
		with IO.open(source, "rb") as InFile:
			if full:
				buffer = bytearray(block)
				for i in range(0, full):
					InFile.readinto(buffer)
					self.Stream.write(buffer)
			if rest:
				buffer = InFile.read(block)
				self.Stream.write(buffer)
				
		return inode

	# Opens a file inside the MIX using MixIO
	# Works like the build-in open function
	def open(self, name, mode="r", buffering=-1, encoding=None, errors=None):
		"!!! STUB !!!"
		#inode = self.get_inode()
		self.files_open.append(id(inode))

# MixIO instaces are used to work with contained files as if they were real
class MixIO(IO.BufferedIOBase):
	# TODO: Realize expand() method in MixFile, not here!
	"Access files inside MIXes as io objects"
	__slots__ = "Controller", "Stream", "__cursor", "__inode"
	
	def __init__(name, container):
		self.Controller = container
		self.Stream     = container.Stream
		self.__inode    = container.get_inode(name)
		self.__cursor   = 0
		
		self.MixFile.files_open.append(id(inode))
		

# Exception for internal errors
class MixError(Exception):
	__slots__ = ()
	
# Exception raised when a Filename is not valid
class MixNameError(ValueError):
	__slots__ = ()
	
class mixnode(object):
	"Inodes used by MixFile instances"
	__slots__ = "name", "offset", "size", "alloc"
	
	def __init__(self, name, offset, size, alloc):
		"Initialize mixnode"
		self.name   = name
		self.offset = offset
		self.size   = size
		self.alloc  = alloc
		
	def __eq__(self, other):
		"Return self is other"
		return self is other
		
	def __ne__(self, other):
		"Return self is not other"
		return self is not other
		
	def __lt__(self, other):
		"Return self.offset < other.offset"
		return self.offset < other.offset
		
	def __le__(self, other):
		"Return self.offset <= other.offset"
		return self.offset <= other.offset
		
	def __gt__(self, other):
		"Return self.offset > other.offset"
		return self.offset > other.offset
		
	def __ge__(self, other):
		"Return self.offset >= other.offset"
		return self.offset >= other.offset
		
	def __len__(self):
		"Return self.alloc or self.size"
		return self.alloc or self.size
		
	def __bool__(self):
		"Return True"
		return True
		
	def __repr__(self):
		"Return string representation"
		return "mixnode({0}, {1}, {2}, {3})".format(
			repr(self.name),
			repr(self.offset),
			repr(self.size),
			repr(self.alloc)
		)
	
	def __delattr__(self, attr):
		"Raise AttributeError"
		raise AttributeError("Can not delete mixnode attribute")

# Create MIX-Identifier from filename
# Thanks to Olaf van der Spek for providing these functions
def genkey(name, mixtype):
	"Compute the key of 'name' according to 'mixtype' and return it"
	name = name.encode("cp1252", "strict")
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
