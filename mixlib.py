#!/usr/bin/env python3
# coding=utf8

# Mixtool – An editor for Westwood Studios’ MIX files
# Copyright © 2015 Bachsau
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

# Constants
TYPE_TD  = 0
TYPE_RA  = 1
TYPE_TS  = 2

BLOCKSIZE = 2097152

ENCODING = "cp1252"

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
		self._Stream = stream
		self._files_open = []
		self._index = {}
		self._contents = []
		self._mixtype = 0
		self.has_checksum = False
		self.is_encrypted = False
		
		# TODO: Fail if Stream is not buffered io
		
		# For new files, initialize mixtype and return
		if new is not None:
			if new < TYPE_TD or new > TYPE_TS:
				raise MixError("Unsupported MIX type")
			self._mixtype = int(new)
			return
			
		filesize = self._Stream.seek(0, IO.SEEK_END)
		if filesize < 4:
			raise MixError("File too small")
			
		# First two bytes are zero for RA/TS and the number of files for TD
		self._Stream.seek(0)
		firstbytes = int.from_bytes(self._Stream.read(2), "little")
		if not firstbytes:
			# It seems we have a RA/TS MIX so decode the flags
			flags = int.from_bytes(self._Stream.read(2), "little")
			self.has_checksum = flags & 1 == 1
			self.is_encrypted = flags & 2 == 2
			
			# Encrypted TS MIXes have a key.ini we can check for later,
			# so at this point assume TYPE_TS only if unencrypted
			self._mixtype = TYPE_RA if self.is_encrypted else TYPE_TS
			
			# Get header data for RA/TS
			if self.is_encrypted:
				# OK, we have to deal with this first
				raise MixError("MIX is encrypted, which ist not yet supported.")
			else:
				# RA/TS MIXes hold their filecount after the flags,
				# whilst for TD MIXes their first two bytes are the filecount.
				filecount = int.from_bytes(self._Stream.read(2), "little")
		else:
			# Maybe it's a TD MIX
			self._mixtype = TYPE_TD
			
			# Get header Data for TD
			filecount = firstbytes
			
		# From here it's the same for every unencrypted MIX
		if not self.is_encrypted:
			bodysize    = int.from_bytes(self._Stream.read(4), "little")
			indexoffset = self._Stream.tell()
			indexsize   = filecount * 12
			bodyoffset  = indexoffset + indexsize
			
			# Check if data is sane
			if filesize - bodyoffset != bodysize:
				raise MixError("Incorrect filesize or invalid header")
				
			# OK, time to read the index
			for i in range(filecount):
				key    = int.from_bytes(self._Stream.read(4), "little")
				offset = int.from_bytes(self._Stream.read(4), "little") + bodyoffset
				size   = int.from_bytes(self._Stream.read(4), "little")
				
				if offset + size > filesize:
					raise MixError("Content " + hex(key) + " out of range")
					
				self._index[key] = mixnode(hex(key), offset, size, size)
				
			if len(self._index) != filecount:
				raise MixError("Duplicate key")
				
		# Now read the names
		for dbkey in (1422054725, 913179935):
			if dbkey in self._index:
				self._Stream.seek(self._index[dbkey].offset)
				header = self._Stream.read(32)
				
				if header != b"XCC by Olaf van der Spek\x1a\x04\x17'\x10\x19\x80\x00":
					continue
				
				dbsize  = int.from_bytes(self._Stream.read(4), "little") # Total filesize
				# Four bytes for XCC type; 0 for LMD, 2 for XIF
				# Four bytes for DB version; Always zero
				self._Stream.seek(8, IO.SEEK_CUR)
				mixtype = int.from_bytes(self._Stream.read(4), "little") # XCC Game ID
				
				if dbsize != self._index[dbkey].size:
					raise MixError("Invalid database")
					
				if mixtype > TYPE_TS + 3:
					raise MixError("Unsupported MIX type")
				elif mixtype > TYPE_TS:
					mixtype = TYPE_TS
					
				self._mixtype = mixtype
				
				namecount = int.from_bytes(self._Stream.read(4), "little")
				bodysize  = dbsize - 53 # Size - header - last byte
				namelist  = self._Stream.read(bodysize).split(b"\x00") if bodysize > 0 else []
				
				if len(namelist) != namecount:
					raise MixError("Invalid database")
					
				# Remove Database from index
				del self._index[dbkey]
				
				# Add names to index
				names = False
				for name in namelist:
					name = name.decode(ENCODING, "ignore")
					key = genkey(name, self._mixtype)
					if key in self._index:
						self._index[key].name = name
						names = True
						
				# XCC sometimes puts two Databases in a file by mistake,
				# so if no names were found, give it another try
				if names: break
				
		# Create a sorted list of all contents
		self._contents = sorted(self._index.values(), key=lambda i: i.offset)
		
		# Calculate alloc values
		# This is the size up to wich a file may grow without needing a move
		for i in range(len(self._contents) - 1):
			self._contents[i].alloc = self._contents[i+1].offset - self._contents[i].offset
			
			if self._contents[i].alloc < self._contents[i].size:
				raise MixError("Overlapping file boundaries")
				
	# Central file-finding method (like stat)
	# Also used to add missing names to the index
	def get_inode(self, name):
		"""
		Return the inode for 'name' or None if not found.
		
		Will save 'name' to the index if missing.
		MixNameError is raised if 'name' is not valid.
		"""
		inode = self._index.get(self.get_key(name))
		
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
				key = genkey(name, self._mixtype)
		except ValueError:
			raise MixNameError("Invalid filename")
			
		return key
		
	def get_contents(self):
		"Return a list of tuples holding the name and size of each file."
		return [(i.name, i.size) for i in self._contents]
		
	# Rename a file in the MIX
	def rename(self, old, new):
		"""
		Rename a file in the MIX.
		
		MixError is raised if the file is not found or a file named 'new' already exists.
		MixNameError is raised if 'name' is not valid.
		"""
		oldkey = self.get_key(old)
		inode = self._index.get(old)
		
		if inode is None:
			raise MixError("File not found")
			
		if inode.name[:2] == "0x":
				inode.name = old
				
		newkey = self.get_key(new)
		
		if newkey in (1422054725, 913179935):
			raise MixNameError("Reserved filename")
			
		existing = self._index.get(newkey)
		
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
		del self._index[oldkey]
		inode.name = new
		self._index[newkey] = inode
		
	# Change MIX type
	def convert(self, newtype):
		"""
		Convert MIX to 'newtype'.
		
		When converting between	TD/RA and TS the MIX is not allowed to have missing
		names as they can not be converted properly. MixError is raised in this	case.
		"""
		if newtype < TYPE_TD or newtype > TYPE_TS + 3:
			raise MixError("Unsupported MIX type")
		elif newtype > TYPE_TS:
			newtype = TYPE_TS
			
		if (newtype >= TYPE_TS and self._mixtype < TYPE_TS)\
		or (newtype < TYPE_TS and self._mixtype >= TYPE_TS):
			# This means we have to generate new keys for all names
			newindex = {}
			for inode in self._contents:
				if inode.name[:2] == "0x":
					raise MixError("Can't convert between TD/RA and TS when names are missing")
					
				newkey = genkey(inode.name, self._mixtype)
				newindex[newkey] = inode
				
			if len(newindex) != len(self._contents):
				raise MixError("Key collision")
				
			self._index = newindex
			
		# Checksum and Encryption is not supported in TD
		if newtype == TYPE_TD:
			self.has_checksum = False
			self.is_encrypted = False
			
		self._mixtype = newtype
		
	# Move contents in stream
	# Not to be called from outside
	def _move_internal(self, rpos, wpos, size):
		"Internal move method"
		full = size // BLOCKSIZE
		rest = size % BLOCKSIZE
		
		if full:
			buffer = bytearray(BLOCKSIZE)
			for i in range(full):
				self._Stream.seek(rpos)
				rpos += self._Stream.readinto(buffer)
				self._Stream.seek(wpos)
				wpos += self._Stream.write(buffer)
				
		if rest:
			self._Stream.seek(rpos)
			buffer = self._Stream.read(rest)
			self._Stream.seek(wpos)
			self._Stream.write(buffer)
			
	# Write current header (Flags, Keysource, Index, Database, Checksum) to MIX
	# TODO: Implement context manager
	def write_index(self, optimize=False):
		"""
		Write current index to file and flush the buffer.
		
		If 'optimize' is given and True, the MIX's contents	will be concatenated
		and overhead removed, so it is ready for distribution.
		"""
		assert len(self._contents) == len(self._index)
		filecount   = len(self._contents)
		indexoffset = 6 if self._mixtype == TYPE_TD else 10
		indexsize   = (filecount + 1) * 12
		bodyoffset  = indexoffset + indexsize
		flags       = 0
		
		# First, anything occupying index space must be moved
		if filecount:
			while self._contents[0].offset < bodyoffset:
				rpos = self._contents[0].offset
				size = self._contents[0].size
				
				# Calculate move block
				i = 0
				while self._contents[i].size == self._contents[i].alloc:
					i += 1
					if i < filecount and self._contents[i].offset < bodyoffset:
						size += self._contents[i].size
					else:
						break
				else:
					i += 1
					
				# Find target position
				index = 0
				for inode in self._contents:
					index += 1
					if inode.alloc - inode.size >= size and inode.offset + inode.size >= bodyoffset:
						# Applies when there's enough spare space
						inode.alloc -= size
						wpos = inode.offset + inode.alloc
						break
				else:
					# This applies when no spare space was found
					index = filecount
					wpos = self._contents[-1].offset + self._contents[-1].alloc
					
				# Update affected inodes
				nextoffset = wpos
				for i in range(i):
					self._contents[0].alloc = self._contents[0].size
					self._contents[0].offset = nextoffset
					nextoffset += self._contents[0].size
					
					self._contents.insert(index, self._contents[0])
					del self._contents[0]
					
				self._move_internal(rpos, wpos, size)
				
			self._contents[-1].alloc = self._contents[-1].size
			
		# Concatenate files if optimize was requested
		if optimize:
			i = 0
			nextoffset = bodyoffset
			while i < filecount:
				inode = self._contents[i]
				
				if inode.offset > nextoffset:
					rpos = inode.offset
					wpos = nextoffset
					
					size = 0
					more = True
					
					while more and i < filecount:
						inode = self._contents[i]
						
						size += inode.size
						more = inode.size == inode.alloc
						
						inode.alloc = inode.size
						inode.offset = nextoffset
						nextoffset += inode.size
						i += 1
					
					self._move_internal(rpos, wpos, size)
					
				else:
					inode.alloc = inode.size
					nextoffset += inode.size
					i += 1
					
		# Write names
		dbsize = 75
		namecount = 1
		dboffset = self._contents[-1].offset + self._contents[-1].alloc if filecount else bodyoffset
		
		self._Stream.seek(dboffset + 52)
		for inode in self._contents:
			if inode.name[:2] != "0x":
				dbsize += self._Stream.write(inode.name.encode(ENCODING, "strict"))
				dbsize += self._Stream.write(b"\x00")
				namecount += 1
		self._Stream.write(b"local mix database.dat\x00")
		self._Stream.truncate()
		
		# Write database header
		self._Stream.seek(dboffset)
		self._Stream.write(b"XCC by Olaf van der Spek\x1a\x04\x17'\x10\x19\x80\x00")
		self._Stream.write(dbsize.to_bytes(4, "little"))
		self._Stream.write(bytes(8))
		self._Stream.write(self._mixtype.to_bytes(4, "little"))
		self._Stream.write(namecount.to_bytes(4, "little"))
		
		# Write index
		bodysize = self._contents[0].offset - bodyoffset if filecount else 0
		files = sorted(self._index.items(), key=lambda i: i[1].offset)
		dbkey = 913179935 if self._mixtype == TYPE_TS else 1422054725
		files.append((dbkey, mixnode(None, dboffset, dbsize, dbsize)))
		
		self._Stream.seek(indexoffset)
		for key, inode in files:
			self._Stream.write(key.to_bytes(4, "little"))
			self._Stream.write((inode.offset - bodyoffset).to_bytes(4, "little"))
			self._Stream.write(inode.size.to_bytes(4, "little"))
			bodysize += inode.alloc
			
		# Write MIX header
		self._Stream.seek(0)
		if self._mixtype != TYPE_TD:
			self._Stream.write(bytes(2))
			self._Stream.write(flags.to_bytes(2, "little"))
		self._Stream.write((filecount + 1).to_bytes(2, "little"))
		self._Stream.write(bodysize.to_bytes(4, "little"))
		
		self._Stream.flush()
		
	# Return if MIX is TD, RA or TS
	def get_type(self):
		"Return a string describing the MIX type. Will be one of TD, RA, TS."
		return ("TD", "RA", "TS")[self._mixtype]
		
	# Get a file out of the MIX
	def get_file(self, name):
		"""
		Return the contents of 'name' as a single bytes object.
		
		MixError is raised if the file is not found.
		"""
		inode = self.get_inode(name)
		
		if inode is None:
			raise MixError("File not found")
			
		self._Stream.seek(inode.offset)
		return self._Stream.read(inode.size)
		
	# Remove a file from the MIX
	def delete(self, name):
		"""
		Remove 'name' from the MIX
		
		MixError is raised if the file is not found.
		MixNameError is raised if 'name' is not valid.
		"""
		key = self.get_key(name)
		inode = self._contents.get(key)
		
		if inode is None:
			raise MixError("File not found")
			
		index = self._contents._index(inode)
		
		if index:
			self._contents[index-1].alloc += inode.alloc
			
		del self._contents[index]
		del self._index[key]
		
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
			
		size = inode.size
		full = size // BLOCKSIZE
		rest = size % BLOCKSIZE
		
		# Alpha protection
		assert not OS.path.isfile(dest)
		
		self._Stream.seek(inode.offset)
		with open(dest, "wb") as OutFile:
			if full:
				buffer = bytearray(BLOCKSIZE)
				for i in range(full):
					self._Stream.readinto(buffer)
					OutFile.write(buffer)
			if rest:
				buffer = self._Stream.read(rest)
				OutFile.write(buffer)
				
	# Insert a new, empty file
	def add_inode(self, name, alloc=4096):
		key = self.get_key(name)
		inode = self._index.get(key)
		
		if inode is not None:
			if inode.name[:2] == "0x":
				inode.name = name
			raise MixError("File exists")
		
		filecount   = len(self._contents)
		indexoffset = 6 if self._mixtype == TYPE_TD else 10
		minoffset   = (filecount + 100) * 12 + indexoffset
		
		if filecount:
			if self._contents[0].offset > minoffset + alloc:
				# Applies when there's much free space at the start
				index = 0
				offset = self._contents[0].offset - alloc
			else:
				index = 0
				for inode in self._contents:
					index += 1
					if inode.alloc - inode.size >= alloc and inode.offset + inode.size >= minoffset:
						# Applies when there's enough spare space anywhere else
						inode.alloc -= alloc
						offset = inode.offset + inode.alloc
						break
				else:
					# This applies when no spare space was found
					index = filecount
					self._contents[-1].alloc = self._contents[-1].size
					offset = self._contents[-1].offset + self._contents[-1].alloc
		else:
			# This applies to empty files
			index = 0
			offset = minoffset
			
		inode = mixnode(name, offset, 0, alloc)
		self._index[key] = inode
		self._contents.insert(index, inode)
		
		return inode
				
	# Insert a file from local filesystem
	def insert(self, name, source):
		"""
		Insert 'source' from the local file system as 'name' and return its inode.
		
		MixError is raised if a file by that name already exists.
		MixNameError is raised if 'name' is not valid.
		"""
		size = OS.stat(source).st_size
		inode = self.add_inode(name, size)
		inode.size = size
		
		full = size // BLOCKSIZE
		rest = size % BLOCKSIZE
		
		self._Stream.seek(inode.offset)
		with open(source, "rb") as InFile:
			if full:
				buffer = bytearray(BLOCKSIZE)
				for i in range(full):
					InFile.readinto(buffer)
					self._Stream.write(buffer)
			if rest:
				buffer = InFile.read(rest)
				self._Stream.write(buffer)
				
		return inode
		
	# Opens a file inside the MIX using MixIO
	# Works like the build-in open function
	def open(self, name, mode="r", buffering=-1, encoding=None, errors=None):
		"!!! STUB !!!"
		
# MixIO instaces are used to work with contained files as if they were real
class MixIO(IO.BufferedIOBase):
	"Access files inside MIXes as io objects"
	__slots__ = "Container", "Stream", "__cursor", "__inode"
	
	def __init__(name, container):
		self.Container = container
		self._Stream    = container._Stream
		self.__inode   = container.get_inode(name)
		self.__cursor  = 0
		
		self.MixFile._files_open.append(id(inode))
		
	# Move some files arround to clear space
	def expand(self, size):
		"Allocate an additional of 'size' bytes"
		
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
		"Return True if node contains valid data, else False"
		return True if (
			isinstance(self.name, str) and
			isinstance(self.offset, int) and
			isinstance(self.size, int) and
			isinstance(self.alloc, int) and
			self.size <= self.alloc
		) else False
		
	def __repr__(self):
		"Return string representation"
		return "mixnode({0}, {1}, {2}, {3})".format(
			repr(self.name),
			repr(self.offset),
			repr(self.size),
			repr(self.alloc)
		)
		
	def __delattr__(self, attr):
		"Raise TypeError"
		raise TypeError("Can't delete mixnode attributes")
		
# Create MIX-Identifier from filename
# Thanks to Olaf van der Spek for providing these functions
def genkey(name, mixtype):
	"""
	Compute the key of 'name' according to 'mixtype' and return it.
	
	This is a low-level function that rarely needs to be used directly.
	"""
	name = name.encode(ENCODING, "strict")
	name = name.upper()
	len_ = len(name)
	
	if mixtype > TYPE_RA:
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
			for j in range(4):
				a >>= 8
				if i < len_:
					a |= (name[i] << 24)
					i += 1
			key = (key << 1 | key >> 31) + a & 4294967295
		return key
