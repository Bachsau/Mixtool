#!/usr/bin/env python3
# coding=utf_8

# Copyright (C) 2015-2018 Sven Heinemann (Bachsau)
#
# This file is part of Mixtool.
#
# Mixtool is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Mixtool is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Mixtool.  If not, see <https://www.gnu.org/licenses/>.

"""Routines to access MIX files."""

__all__ = ["MixError", "MixParseError", "MixFSError", "MixIOError", "Version", "MixRecord", "MixFile", "MixIO", "genkey"]
__version__ = "0.2.0-volatile"
__author__ = "Bachsau"

import sys
import os
import io
import collections
import enum
import binascii


# Constants
BLOCKSIZE: int = 2097152  # 2 MiB
ENCODING: str = "cp1252"  # Western Windows


# MixNodes are lightweight objects to store a defined set of index data
class _MixNode(object):
	"""Nodes used by MixFile instances to store index data."""
	
	__slots__ = ("key", "offset", "size", "alloc", "name", "links")

	def __init__(self, key: int, offset: int, size: int, alloc: int, name: str) -> None:
		"""Initialize the node."""
		self.key    = key
		self.offset = offset
		self.size   = size
		self.alloc  = alloc
		self.name   = name
		self.links  = 0

	def __repr__(self) -> str:
		"""Return string representation."""
		return "_MixNode({0!r}, {1!r}, {2!r}, {3!r}, {4!r})".format(
			self.key, self.offset, self.size, self.alloc, self.name
		)

	def __delattr__(self, attr: str) -> None:
		"""Raise `TypeError`."""
		raise TypeError("Can't delete node attributes.")


class MixError(Exception):
	"""Base exception for all MIX related errors."""
	# TODO: Add errnos, errstrs, filename attributes and subclassig.
	__slots__ = ("errno", "strerror", "filename", "filename2")
	
	def __init__(self, *args):
		self.errno = None
		self.strerror = None
		self.filename = None
		self.filename2 = None
	
	def __str__(self):
		if self.errno is not None and self.strerror is not None:
			return "[Errno {0!s}] {1!s}".format(self.errno, self.strerror)
		return Exception.__str__(self)


class MixParseError(MixError):
	"""Exception raised on errors in the MIX file."""
	__slots__ = ()


class MixFSError(MixError):
	"""Exception raised on errors on content access."""
	__slots__ = ()


class MixIOError(MixError):
	"""Exception raised on invalid MixIO operations."""
	__slots__ = ()


# MIX versions
class Version(enum.Enum):
	"""Enumeration of MIX versions, named after the various games."""
	
	TD  = 0  # Tiberian Dawn
	RA  = 1  # Red Alert
	TS  = 2  # Tiberian Sun
	RA2 = 2  # Red Alert 2
	YR  = 2  # Yuri's Revenge
	RG  = 3  # Renegade
	
	def __lt__(self, other) -> bool:
		"""Return True if `self` is a lower version than `other`."""
		if type(self) is type(other):
			return self._value_ < other._value_
		else:
			return NotImplemented
	
	def __le__(self, other) -> bool:
		"""Return True if `self` is a lower or the same version as `other`."""
		if type(self) is type(other):
			return self._value_ <= other._value_
		else:
			return NotImplemented
	
	def __gt__(self, other) -> bool:
		"""Return True if `self` is a higher version than `other`."""
		if type(self) is type(other):
			return self._value_ > other._value_
		else:
			return NotImplemented
	
	def __ge__(self, other) -> bool:
		"""Return True if `self` is a higher or the same version as `other`."""
		if type(self) is type(other):
			return self._value_ >= other._value_
		else:
			return NotImplemented
	
	def needs_conversion(self, other) -> bool:
		"""Tell if keys need to be recalculated when converting to `other`."""
		try:
			if self <= Version.RA:
				return other > Version.RA
			return other < Version.TS
		except TypeError:
			raise TypeError("Operands must be members of Version.") from None


# A named tuple for metadata returned to the user
MixRecord = collections.namedtuple("MixRecord", ("name", "size", "offset", "alloc", "node_id"))


# Instances represent a single MIX file.
# They are refered to as "containers".
class MixFile(object):
	"""Manage MIX files, one file per instance."""
	
	__slots__ = ("_dirty", "_stream", "_open", "_index", "_contents", "_version", "_flags")
	
	def __init__(self, stream: io.BufferedIOBase, version: Version = None) -> None:
		"""Parse a MIX from `stream`, which must be a buffered file object.
		
		If `version` is given, initialize an empty MIX of this version instead.
		`MixParseError` is raised on parsing errors.
		"""
		
		# Initialize mandatory attributes
		self._dirty = False
		self._stream = None
		self._open = []
		
		# If stream is, for example, a raw I/O object, files could be destroyed
		# without ever raising an error, so check this.
		if not isinstance(stream, io.BufferedIOBase):
			raise TypeError("`stream` must be an instance of io.BufferedIOBase.")
		
		if not stream.readable():
			raise ValueError("`stream` must be readable.")
		
		if not stream.seekable():
			raise ValueError("`stream` must be seekable.")
		
		if version is not None:
			# Create a new file
			if type(version) is not Version:
				raise TypeError("`version` must be a member of Version or None.")
			self._stream = stream
			self._index = {}
			self._contents = []
			self._version = version
			self._flags = 0
			return
		
		# Parse an existing file
		filesize = stream.seek(0, io.SEEK_END)
		if filesize <= 6:
			raise MixParseError("File too small.")
		stream.seek(0)
		
		first4 = stream.read(4)
		if first4 == b"MIX1":
			raise NotImplementedError("RG MIX files are not yet supported.")
		elif first4[:2] == b"\x00\x00":
			# It seems we have a RA/TS MIX so check the flags
			flags = first4[2]
			if flags > 3:
				raise MixParseError("Invalid file flags.")
			if flags & 2:
				raise NotImplementedError("Encrypted MIX files are not yet supported.")
			
			# Encrypted TS MIXes have a key.ini we can check for later,
			# so at this point assume Version.TS only if unencrypted
			version = Version.TS
			
			# RA/TS MIXes hold their filecount after the flags,
			# whilst for TD MIXes their first two bytes are the filecount.
			filecount = int.from_bytes(stream.read(2), "little")
		else:
			version = Version.TD
			flags = 0
			filecount = int.from_bytes(first4[:2], "little")
			stream.seek(2)
			
		# From here it's the same for every unencrypted MIX
		bodysize    = int.from_bytes(stream.read(4), "little")
		indexoffset = stream.tell()
		indexsize   = filecount * 12
		bodyoffset  = indexoffset + indexsize

		# Check if data is sane
		if filesize - bodyoffset != bodysize:
			raise MixParseError("Incorrect filesize or invalid header.")

		# OK, time to read the index
		index = {}
		for i in range(filecount):
			key    = int.from_bytes(stream.read(4), "little")
			offset = int.from_bytes(stream.read(4), "little") + bodyoffset
			size   = int.from_bytes(stream.read(4), "little")

			if offset + size > filesize:
				raise MixParseError("Content extends beyond end of file.")

			index[key] = _MixNode(key, offset, size, size, None)

		if len(index) != filecount:
			raise MixError("Duplicate key.")

		# Now read the names
		# TD/RA: 1422054725; TS: 913179935
		for dbkey in (1422054725, 913179935):
			if dbkey in index:
				stream.seek(index[dbkey].offset)
				header = stream.read(32)

				if header != b"XCC by Olaf van der Spek\x1a\x04\x17'\x10\x19\x80\x00":
					continue

				dbsize  = int.from_bytes(stream.read(4), "little")  # Total filesize

				if dbsize != index[dbkey].size or dbsize > 16777216:
					raise MixParseError("Invalid database.")

				# Skip four bytes for XCC type; 0 for LMD, 2 for XIF
				# Skip four bytes for DB version; Always zero
				stream.seek(8, io.SEEK_CUR)
				gameid = int.from_bytes(stream.read(4), "little")  # XCC Game ID
				
				# XCC saves alias numbers, so converting them
				# to `Version` is not straight forward.
				# FIXME: Check if Dune games and Nox also use MIX files
				if gameid == 0:
					if version is not Version.TD:
						continue
				elif gameid == 1:
					version = Version.RA
				elif 2 <= gameid <= 6 or gameid == 15:
					version = Version.TS
				else:
					continue
				
				namecount = int.from_bytes(stream.read(4), "little")
				bodysize  = dbsize - 53  # Size - Header - Last byte
				namelist  = stream.read(bodysize).split(b"\x00") if bodysize > 0 else []
				
				if len(namelist) != namecount:
					raise MixError("Invalid database.")
				
				# Remove Database from index
				del index[dbkey]
				
				# Add names to index
				names = False
				for name in namelist:
					name = name.decode(ENCODING, "ignore")
					key = genkey(name, version)
					if key in index:
						index[key].name = name
						names = True
				
				# XCC sometimes puts two Databases in a file by mistake,
				# so if no names were found, give it another try
				if names: break

		# Create a sorted list of all contents
		contents = sorted(index.values(), key=lambda node: node.offset)

		# Calculate alloc values
		# This is the size up to wich a file may grow without needing a move
		for i in range(len(contents) - 1):
			contents[i].alloc = contents[i+1].offset - contents[i].offset

			if contents[i].alloc < contents[i].size:
				raise MixError("Overlapping file boundaries.")

		# Populate the object
		self._stream = stream
		self._version = version
		self._index = index
		self._contents = contents
		self._flags = flags
		
	# Object destruction method
	def finalize(self) -> io.BufferedIOBase:
		"""Finalize the container and return its stream."""
		# TODO: Close all contained files as soon as
		#       `self.open()` gets implemented.
		if self._dirty:
				self.write_index()
		stream = self._stream
		self._stream = None
		stream.seek(0)
		return stream

	# Dirty bit is only used to prevent file corruption,
	# not for index-only changes like renames, etc.
	def __del__(self) -> None:
		"""Call `self.write_index()` if in inconsistent state.
		
		Suppress any errors as they occur.
		"""
		try:
			if self._stream is not None:
				print("MixFile object destroyed without being finalized.", file=sys.stderr)
				if self._dirty and not self._stream.closed():
					self.write_index()
		except Exception:
			pass

	# Central file-finding method
	# Also used to add missing names to the index
	def _get_node(self, name: str) -> _MixNode:
		"""Return the inode for 'name' or 'None' if not found.

		Save 'name' in the inode if missing.
		'MixNameError' is raised if 'name' is not valid.
		"""
		
		inode = self._index.get(self._get_key(name))

		if inode is not None and inode.name is None and not name.startswith("0x"):
				inode.name = name

		return inode

	# Get key for any _valid_ name
	def _get_key(self, name: str) -> int:
		"""Return the key for 'name', regardless of it being in the MIX.

		'MixNameError' is raised if 'name' is not valid.
		"""
		
		if not name:
			raise MixNameError("Filename must not be empty.")

		try:
			if name.startswith("0x"):
				key = int(name, 16)
			else:
				key = genkey(name, self._version)
		except ValueError:
			raise MixNameError("Invalid filename.")
			# FIXME: Parameters could be added to distinguish between encoding
			#        and hex conversion errors, when MixNameError matures.

		return key
		
		
	# Move contents in stream
	# Not to be called from outside
	def _move_internal(self, rpos, wpos, size):
		"""Internal move method..."""
		
		full = size // BLOCKSIZE
		rest = size % BLOCKSIZE

		if full:
			buffer = bytearray(BLOCKSIZE)
			for i in range(full):
				self._stream.seek(rpos)
				rpos += self._stream.readinto(buffer)
				self._stream.seek(wpos)
				wpos += self._stream.write(buffer)

		if rest:
			self._stream.seek(rpos)
			buffer = self._stream.read(rest)
			self._stream.seek(wpos)
			self._stream.write(buffer)
	
	def _reposition(file):
		pass
	
	# Public method to list the MIX file's contents
	def get_contents(self) -> list:
		"""Return a list of tuples holding the attributes of each file."""
		return [MixRecord(hex(node.key) if node.name is None else node.name, node.size, node.offset, node.alloc, id(node)) for node in self._contents]
		
	# Public method to stat a file
	# Replaces get_inode() to the public
	def get_info(self, name: str) -> MixRecord:
		"""Return a tuple holding the attributes of the file called `name`."""
		raise NotImplementedError("Stub method")
	
	
	# Public method to get the filecount,
	# so one doesn't need to run len(self.get_contents()).
	def get_filecount(self) -> int:
		"""Return the number of files in the MIX."""
		return len(self._contents)
		
		
	# Public method to get the MIX version
	def get_version(self) -> Version:
		"""Return MIX version."""
		return self._version
			
			
	# Public method to add missing names
	def test(self, name: str):
		"""Return 'True' if a file of 'name' is in the MIX, else 'False'.
		
		Add 'name' to the index if missing.
		'MixNameError' is raised if 'name' is not valid.
		"""
		
		return False if self._get_node(name) is None else True
		
	
	# Rename a file in the MIX (New method)
	def rename(self, old_name: str, new_name: str) -> bool:
		"""Rename a contained file and return `True` if there were any changes.
		
		`ValueError` is raised if any name is not valid.
		
		`MixInternalError` is raised if `old_name` does not exist,
		`new_name` already exists or a key collision occurs.
		"""
	
	
	# Rename a file in the MIX (FUBAR method)
	def rename_old(self, old_name, new_name):
		"""Rename a file in the MIX.
		
		!!! BROKEN !!!
		"""
		
		raise NotImplementedError("FUBAR")
		
		oldkey = self._get_key(old)
		inode = self._index.get(old)

		if inode is None:
			raise MixError("File not found")

		if inode.name.startswith("0x"):
				inode.name = old

		newkey = self._get_key(new)

		if newkey in (1422054725, 913179935):
			raise MixNameError("Reserved filename")

		existing = self._index.get(newkey)

		if existing:
			if existing is inode:
				# This  means "old" and "new" matched the same key.
				if not new.startswith("0x"):
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
	# TODO: Repair
	def convert(self, version: Version):
		"""Convert MIX to `version`.

		When converting between	TD/RA and TS, the MIX is not allowed to have missing
		names as they can not be converted properly. MixError is raised in that	case.
		"""
		
		if newtype < Version.TD or newtype > Version.TS + 3:
			raise MixError("Unsupported MIX type")
		elif newtype > Version.TS:
			newtype = Version.TS

		if (newtype >= Version.TS and self._version < Version.TS)\
		or (newtype < Version.TS and self._version >= Version.TS):
			# This means we have to generate new keys for all names
			newindex = {}
			for inode in self._contents:
				if inode.name.startswith("0x"):
					raise MixError("Can't convert between TD/RA and TS when names are missing")

				newkey = genkey(inode.name, self._version)
				newindex[newkey] = inode

			if len(newindex) != len(self._contents):
				raise MixError("Key collision")

			self._index = newindex

		# Checksum and Encryption is not supported in TD
		if newtype == Version.TD:
			self.has_checksum = False
			self.is_encrypted = False

		self._version = newtype


	# Write current header (Flags, Keysource, Index, Database, Checksum) to MIX
	# TODO: Implement context manager
	def write_index(self, optimize: bool = False):
		"""Write current index to file and flush the buffer.

		If 'optimize' is given and true, the MIX's contents will be concatenated
		and overhead removed, so it is ready for distribution.
		"""
		
		assert len(self._contents) == len(self._index)
		filecount   = len(self._contents)
		indexoffset = 6 if self._version == Version.TD else 10
		indexsize   = (filecount + 1) * 12
		bodyoffset  = indexoffset + indexsize
		# TODO: Implement checksum and encryption
		flags       = 0

		# First, anything occupying index space must be moved
		# FIXME: A lot of confusing list editing happens here
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

		self._stream.seek(dboffset + 52)
		for inode in self._contents:
			if inode.name is not None:
				dbsize += self._stream.write(inode.name.encode(ENCODING, "strict"))
				dbsize += self._stream.write(b"\x00")
				namecount += 1
		self._stream.write(b"local mix database.dat\x00")
		self._stream.truncate()

		# Write database header
		self._stream.seek(dboffset)
		self._stream.write(b"XCC by Olaf van der Spek\x1a\x04\x17'\x10\x19\x80\x00")
		self._stream.write(dbsize.to_bytes(4, "little"))
		self._stream.write(bytes(8))
		self._stream.write(self._version.to_bytes(4, "little"))
		self._stream.write(namecount.to_bytes(4, "little"))

		# Write index
		bodysize = self._contents[0].offset - bodyoffset if filecount else 0
		files = sorted(self._index.items(), key=lambda i: i[1].offset)
		dbkey = 1422054725 if self._version < Version.TS else 913179935
		files.append((dbkey, _MixNode(None, dboffset, dbsize, dbsize)))

		self._stream.seek(indexoffset)
		for key, inode in files:
			self._stream.write(key.to_bytes(4, "little"))
			self._stream.write((inode.offset - bodyoffset).to_bytes(4, "little"))
			self._stream.write(inode.size.to_bytes(4, "little"))
			bodysize += inode.alloc

		# Write MIX header
		self._stream.seek(0)
		if self._version != Version.TD:
			self._stream.write(bytes(2))
			self._stream.write(flags.to_bytes(2, "little"))
		self._stream.write((filecount + 1).to_bytes(2, "little"))
		self._stream.write(bodysize.to_bytes(4, "little"))

		self._stream.flush()

	# Get a file out of the MIX
	def get_file(self, name):
		"""Return the contents of 'name' as a single bytes object.

		'MixError' is raised if the file is not found.
		"""
		
		inode = self._get_node(name)

		if inode is None:
			raise MixError("File not found")

		self._stream.seek(inode.offset)
		return self._stream.read(inode.size)

	# Remove a file from the MIX
	def delete(self, name):
		"""Remove 'name' from the MIX

		'MixError' is raised if the file is not found.
		'MixNameError' is raised if 'name' is not valid.
		"""
		
		key = self._get_key(name)
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
		"""Extract 'name' to 'dest' on the local file system.

		Existing files will be overwritten.
		'MixError' is raised if the file is not found.
		'MixNameError' is raised if 'name' is not valid.
		"""
		
		inode = self._get_node(name)

		if inode is None:
			raise MixError("File not found")

		size = inode.size
		full = size // BLOCKSIZE
		rest = size % BLOCKSIZE

		self._stream.seek(inode.offset)
		with open(dest, "wb") as OutFile:
			if full:
				buffer = bytearray(BLOCKSIZE)
				for i in range(full):
					self._stream.readinto(buffer)
					OutFile.write(buffer)
			if rest:
				buffer = self._stream.read(rest)
				OutFile.write(buffer)

	# Insert a new, empty file
	def add_inode(self, name, alloc=4096):
		key = self._get_key(name)
		inode = self._index.get(key)

		if inode is not None:
			if inode.name.startswith("0x"):
				inode.name = name
			raise MixError("File exists.")

		filecount   = len(self._contents)
		indexoffset = 6 if self._version == Version.TD else 10
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

		inode = _MixNode(name, offset, 0, alloc)
		self._index[key] = inode
		self._contents.insert(index, inode)

		return inode

	# Insert a file from local filesystem
	def insert_file(self, path: str, name: str) -> None:
		"""Insert 'path' from the local file system as 'name'.

		`MixInternalError` is raised if a file by that name already exists.
		`ValueError` is raised if 'name' is not valid.
		"""
		size = os.stat(source).st_size
		inode = self.allocate(name, size)
		inode.size = size

		full = size // BLOCKSIZE
		rest = size % BLOCKSIZE

		self._stream.seek(inode.offset)
		with open(source, "rb") as InFile:
			if full:
				buffer = bytearray(BLOCKSIZE)
				for i in range(full):
					InFile.readinto(buffer)
					self._stream.write(buffer)
			if rest:
				buffer = InFile.read(rest)
				self._stream.write(buffer)
	
	# Create a file out of bytes
	def insert_bytes(self, data: bytes, name: str) -> None:
		"""!!! STUB !!!"""
		raise NotImplementedError("Stub method")
	
	# Opens a file inside the MIX using MixIO
	# Works like the build-in open function
	def open(self, name: str, mode: str = "r", buffering: int = -1, encoding: str = None, errors: str = None, newline: str = None):
		"""!!! STUB !!!"""
		raise NotImplementedError("Stub method")
	
	@property
	def has_checksum(self) -> bool:
		"""Define if MIX has a checksum."""
		return bool(self._flags & 1)
	
	@has_checksum.setter
	def has_checksum(self, value: bool):
		"""Define if MIX has a checksum."""
		if self._version is not Version.TD:
			if value:
				self._flags |= 1
			else:
				self._flags &= -2
	
	@property
	def is_encrypted(self) -> bool:
		"""Define if MIX headers are encrypted."""
		return bool(self._flags & 2)
	
	@is_encrypted.setter
	def is_encrypted(self, value: bool):
		"""Define if MIX headers are encrypted."""
		if self._version is not Version.TD:
			if value:
				self._flags |= 2
			else:
				self._flags &= -3


# MixIO instaces are used to work with contained files as if they were real
class MixIO(io.BufferedIOBase):
	"""Access files inside MIXes like files on disk."""
	
	__slots__ = ("_container", "_node", "__cursor", "__readable", "__writeable")
	
	def __init__(self, container: MixFile, name: str, flags: int) -> None:
		"""Initialize an abstract stream for `name` on top of `container`."""
		self._container = container
		self._node = container._get_node(name)
		# FIXME: This should probably raise ValueError instead of failing silently on container error
		self.__readable = flags & 1 and container._stream.readable()
		self.__writeable = flags & 2 and container._stream.writeable()
		self.__cursor = 0
		self._node.links += 1
	
	def readable(self) -> bool:
		# FIXME: Check if we can exchange OSError by MixIOError
		"""Return True if the stream can be read from. If False, read() will raise OSError."""
		if self.closed:
			raise ValueError("I/O operation on closed file")

		return self._container._stream.readable()
	
	def writeable(self) -> bool:
		"""Return True if the stream supports writing. If False, write() and truncate() will raise OSError."""
		if self.closed:
			raise ValueError("I/O operation on closed file")

		return self.__writeable()
	
	def seekable(self):
		"""Return True"""
		return True
	
	def close(self):
		"""
		Flush and close this stream.

		This method has no effect if the file is already closed. Once the file is closed,
		any operation on the file (e.g. reading or writing) will raise `ValueError`.
		"""
		if not self.closed:
			self._node.links -= 1
			self._container = None
			self._node = None
	
	@property
	def closed(self):
		"""Return `True` if the stream is closed."""
		return self._container is None or self._node is None


# Create MIX-Identifier from filename
# Thanks to Olaf van der Spek for providing these functions
def genkey(name: str, version: Version) -> int:
	"""Return the key for `name` according to `version`.

	This is a low-level function that rarely needs to be used directly.
	"""
	name = name.encode(ENCODING, "strict").upper()
	len_ = len(name)
	
	if version <= Version.RA:
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
	else:
		# Compute key for TS MIXes
		a = len_ & ~3
		if len_ & 3:
			name += bytes((len_ - a,))
			name += bytes((name[a],)) * (3 - (len_ & 3))
		return binascii.crc32(name)
