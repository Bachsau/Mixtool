#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#﻿ Copyright (C) 2015-2019 Sven Heinemann (Bachsau)
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

__all__ = [
	"MixError",
	"MixParseError",
	"MixFSError",
	"MixReadOnlyError",
	"MixNotFoundError",
	"MixExistsError",
	"MixReservedError",
	"Version",
	"MixRecord",
	"MixFile",
	"MixIO",
	"genkey"
]
__version__ = "0.2.0-volatile"
__author__ = "Bachsau"

# Standard modules
import sys
import os
import io
import collections
import enum
import struct
import binascii


# Constants
BLOCKSIZE: int = 2097152  # 2 MiB
ENCODING: str = "cp1252"  # Western Windows


# MixNodes are lightweight objects to store a defined set of index data
class _MixNode(object):
	"""Nodes used by MixFile instances to store index data."""
	
	__slots__ = ("key", "offset", "size", "alloc", "name", "links")

	def __init__(self, key: int, offset: int, size: int, alloc: int, name: str):
		"""Initialize the node."""
		self.key    = key
		self.offset = offset
		self.size   = size
		self.alloc  = alloc
		self.name   = name
		self.links  = 0

	def __repr__(self):
		"""Return string representation."""
		return "_MixNode({0!r}, {1!r}, {2!r}, {3!r}, {4!r})".format(
			self.key, self.offset, self.size, self.alloc, self.name
		)

	def __delattr__(self, attr):
		"""Raise TypeError."""
		raise TypeError("Cannot delete node attributes.")


class MixError(Exception):
	"""Base exception for all MIX related errors."""


class MixParseError(MixError):
	"""Exception raised on errors while loading a MIX file."""


# A custom exception class that closely resembles Python's OSError
class MixFSError(MixError):
	"""MixFSError(errno: int, strerror: str, filename: str, filename2: str)
	
	Base exception for errors on content access.
	"""
	
	__slots__ = ("_characters_written", "errno", "filename", "filename2", "strerror")
	
	__errnomap = None
	
	def __new__(cls, *args):
		"""Return a new instance of MixFSError or one of its subclasses.
		
		The subclass is chosen based on the value of the first argument,
		as long as a second argument is present.
		"""
		if cls is MixFSError and 2 <= len(args) <= 4:
			if cls.__errnomap is None:
				cls.__errnomap = {
					1: MixReadOnlyError,  # Container not writable
					2: MixNotFoundError,  # File not found
					3: MixExistsError,    # File exists
					4: MixReservedError   # Reserved key (name tables)
				}
			newcls = cls.__errnomap.get(args[0])
			if newcls is not None:
				return newcls(*args)
		
		# Initialize special attributes
		self = super().__new__(cls, *args)
		for attr in MixFSError.__slots__:
			setattr(self, attr, None)
		return self
	
	def __init__(self, *args):
		"""Initialize MixFSError with the given values."""
		a = len(args)
		if 2 <= a <= 4:
			self.errno = args[0]
			self.strerror = args[1]
			if a > 2:
				self.args = args[:2]
				self.filename = args[2]
				if a > 3:
				 self.filename2 = args[3]
	
	def __delattr__(self, attr):
		"""Delete the attribute if it’s not a special one, else set it to None."""
		if attr in MixFSError.__slots__:
			setattr(self, attr, None)
		else:
			super().__delattr__(attr)
	
	def __str__(self):
		"""Return string representation."""
		if self.errno is not None and self.strerror is not None:
			return "[Errno {0!s}] {1!s}".format(self.errno, self.strerror)
		return super().__str__()
	
	@property
	def characters_written(self) -> int:
		"""The number of characters written before the error occurred."""
		if self._characters_written is None:
			raise AttributeError("characters_written")
		return self._characters_written
	
	@characters_written.setter
	def characters_written(self, value: int) -> None:
		"""The number of characters written before the error occurred."""
		if type(value) is int:
			self._characters_written = value
			return
		try:
			value = value.__index__()
		except Exception:
			# OSError does it more or less the same way
			pass
		else:
			if type(value) is int:
				self._characters_written = value
				return
		raise TypeError("Value cannot be interpreted as an integer.")
	
	@characters_written.deleter
	def characters_written(self) -> None:
		"""The number of characters written before the error occurred."""
		self._characters_written = None


class MixReadOnlyError(MixFSError):
	"""Raised when trying to run write operations in read-only containers.
	
	See help(MixFSError) for accurate signature.
	"""


class MixNotFoundError(MixFSError):
	"""Raised when content is requested that doesn’t exist.
	
	See help(MixFSError) for accurate signature.
	"""


class MixExistsError(MixFSError):
	"""Raised when trying to set a name evaluating to an existing key.
	
	See help(MixFSError) for accurate signature.
	"""


class MixReservedError(MixFSError):
	"""Raised when trying to set a name evaluating to a reserved key.
	
	See help(MixFSError) for accurate signature.
	"""


# MIX versions
class Version(enum.Enum):
	"""Enumeration of MIX versions, named after the various games."""
	
	TD  = 0  # Tiberian Dawn
	RA  = 1  # Red Alert
	TS  = 2  # Tiberian Sun
	RA2 = 2  # Red Alert 2
	YR  = 2  # Yuri's Revenge
	RG  = 3  # Renegade
	
	def needs_conversion(self, other) -> bool:
		"""Tell if keys need to be recalculated when converting to `other`."""
		if type(self) is Version and type(other) is Version:
			lowers = (Version.TD, Version.RA)
			if self in lowers:
				return other not in lowers
			return self is not other
		raise TypeError("Operands must be Version enumeration members.")


# A named tuple for metadata returned to the user
MixRecord = collections.namedtuple("MixRecord", ("name", "size", "alloc", "offset"))


# Instances represent a single MIX file.
# They are refered to as "containers".
class MixFile(object):
	"""Manage MIX files, one file per instance."""
	
	__slots__ = ("_dirty", "_stream", "_open", "_index", "_contents", "_version", "_flags")
	
	def __init__(self, stream: io.BufferedIOBase, version: Version = None):
		"""Parse a MIX from `stream`, which must be a buffered file object.
		
		If `version` is given, initialize an empty MIX of this version instead.
		MixParseError is raised on parsing errors.
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
			# Start empty (new file)
			if type(version) is not Version:
				raise TypeError("`version` must be a Version enumeration member or None.")
			if version is Version.RG:
				raise NotImplementedError("RG MIX files are not yet supported.")
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
			# It seems we have a RA or TS MIX so check the flags
			flags = int.from_bytes(first4[2:], "little")
			if flags > 3:
				raise MixParseError("Unsupported properties.")
			if flags & 2:
				raise NotImplementedError("Encrypted MIX files are not yet supported.")
			
			# FIXME HERE: 80 bytes of westwood key_source if encrypted,
			#             to create a 56 byte long blowfish key from it.
			#
			#             They are followed by a number of 8 byte blocks,
			#             the first of them decrypting to filecount and bodysize.
			
			# Encrypted TS MIXes have a key.ini we can check for later,
			# so at this point assume Version.TS only if unencrypted.
			# Stock RA MIXes seem to be always encrypted.
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
		# FIXME: Checksummed MIXes have 20 additional bytes after the body.
		if filesize - bodyoffset != bodysize:
			raise MixParseError("Incorrect filesize or invalid header.")

		# OK, time to read the index
		index = {}
		for key, offset, size in struct.iter_unpack("<LLL", stream.read(indexsize)):
			offset += bodyoffset
			
			if offset + size > filesize:
				raise MixParseError("Content extends beyond end of file.")

			index[key] = _MixNode(key, offset, size, size, None)

		if len(index) != filecount:
			raise MixParseError("Duplicate key.")

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
					raise MixParseError("Invalid name table.")

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
				namelist  = stream.read(bodysize).split(b"\x00") if bodysize else []
				
				if len(namelist) != namecount:
					raise MixParseError("Invalid name table.")
				
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
				raise MixParseError("Overlapping file boundaries.")

		# Populate the object
		self._stream = stream
		self._version = version
		self._index = index
		self._contents = contents
		self._flags = flags
	
	def _allocate(node: _MixNode, space: int) -> None:
		"""Allocate an amount of `space` bytes to `node` in addition to its size."""
		# Move, expand, etc...
	
	def create(name: str, alloc: int = 0) -> None:
		"""Create a contained file and optionally pre-allocate some bytes to it.
		
		The resulting file might have a greater amount of space allocated to it,
		but never less.
		"""
	
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
		"""Call self.write_index() if in inconsistent state.
		
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
		"""Return the node for `name` or None if not found.

		Add `name` to the node if it’s missing.
		
		ValueError is raised if `name` is not valid.
		"""
		node = self._index.get(self._get_key(name))
		if node is not None and node.name is None and not name.startswith(("0x", "0X")):
				node.name = name
		return node
	
	# Get key for any *valid* name
	def _get_key(self, name: str) -> int:
		"""Return the key for `name`, regardless of it being in the MIX.

		ValueError is raised if `name` is not valid.
		"""
		if not isinstance(name, str):
			raise TypeError("Names must be strings.")
		
		if not name:
			raise ValueError("Names must not be empty.")
		
		if name.startswith(("0x", "0X")):
			key = int(name, 16)
			if not key:
				raise ValueError("Keys must not be zero.")
			if key > 4294967295:
				raise ValueError("Key exceeds maximum value.")
			return key
		return genkey(name, self._version)
		
		
	# Move contents in stream
	# Not to be called from outside
	def _move_internal(self, rpos, wpos, size):
		"""Internal move method..."""
		
		blocks, rest = divmod(size, BLOCKSIZE)

		if blocks:
			buffer = bytearray(BLOCKSIZE)
			for i in range(blocks):
				self._stream.seek(rpos)
				rpos += self._stream.readinto(buffer)
				self._stream.seek(wpos)
				wpos += self._stream.write(buffer)

		if rest:
			self._stream.seek(rpos)
			buffer = self._stream.read(rest)
			self._stream.seek(wpos)
			self._stream.write(buffer)
	
	# Public method to list the MIX file's contents
	def get_contents(self) -> list:
		"""Return a list of tuples holding the attributes of each file."""
		return [MixRecord(
			node.name or hex(node.key),
			node.size,
			node.alloc,
			node.offset
		) for node in self._contents]
	
	def get_overhead(self) -> int:
		"""Return the amount of unused space in the MIX file."""
		# TODO: Implement
		raise NotImplementedError("Stub method")
	
	# Public version of get_node()
	def stat(self, name: str) -> MixRecord:
		"""Return a tuple holding the attributes of the file called `name`."""
		# TODO: Implement
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
		"""Return True if the MIX contains a file of `name`, else False.
		
		Add `name` to its node if it’s missing.
		
		ValueError is raised if `name` is not valid.
		"""
		return self._get_node(name) is not None
	
	# Rename a file in the MIX (New method)
	def rename(self, old: str, new: str) -> bool:
		"""Rename a contained file and return True if there were any changes.
		
		ValueError is raised if any name is not valid.
		
		MixFSError is raised if a file named `old` does not exist,
		a file named `new` already exists or a key collision occurs.
		"""
		oldkey = self._get_key(old)
		node = self._index.get(oldkey)
		
		if node is None:
			raise MixFSError(2, old, None, "File not found")
		
		if old == new:
			# Maybe the user wants to add a missing name
			# by giving it twice...
			if node.name is None and not new.startswith(("0x", "0X")):
				node.name = new
				return True
			return False
		
		newkey = self._get_key(new)
		
		if newkey == oldkey:
			# We already know that `old` exists,
			# so `old` and `new` refer to the same file.
			if new.startswith(("0x", "0X")):
				# We do not delete names
				return False
			# Changed casing, a key-equivalent
			# or a matching name for a key-only file.
			node.name = new
			return True
		
		conflict_node = self._index.get(newkey)
		if conflict_node is not None:
			# In this case a different file named `new` already exists,
			# but we never miss a chance to add missing names
			if node.name is None and not old.startswith(("0x", "0X")):
				node.name = old
			if conflict_node.name is None:
				conflict_name = hex(conflict_node.key)
				if not new.startswith(("0x", "0X")):
					conflict_node.name = new
			else:
				conflict_name = conflict_node.name
			raise MixFSError(3, new, conflict_name, "File exists")
		
		if newkey in (1422054725, 913179935):
			# These are namelists
			raise MixFSError(4, new, None, "Evaluation to reserved key")
		
		# Checks complete. It's going to be a "real" name change
		del self._index[oldkey]
		self._index[newkey] = node
		node.key = newkey
		node.name = None if new.startswith(("0x", "0X")) else new

	# Change MIX version
	def set_version(self, version: Version):
		"""Change MIX file format to `version`.

		When not converting between TD and RA, the MIX is not allowed to have
		missing	names as they can not be converted properly.
		MixFSError is raised in that case.
		"""
		if self._version.needs_conversion(version):
			# This means we have to generate new keys for all names
			newindex = {}
			reserved = (1422054725, 913179935)
			for node in self._contents:
				if node.name is None:
					raise MixFSError("Conversion impossible with names missing.")
				
				newkey = genkey(node.name, version)
				if newkey in reserved:
					# These are namelists
					raise MixFSError("Evaluation to reserved key")
				newindex[newkey] = node
			
			if len(newindex) != len(self._contents):
				raise MixFSError("Key collision")
			
			self._index = newindex
			
			for key, node in self._index:
				node.key = key
		
		if version is Version.TD:
			# Flags are not supported by TD MIXes
			self._flags = 0
		
		self._version = version


	# Write current header (Flags, Keysource, Index, Database, Checksum) to MIX
	# TODO: Implement context manager
	def write_index(self, optimize: bool = False):
		"""Write current index to file and flush the buffer.

		If `optimize` is given and true, the MIX’s contents will be concatenated
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
		dbkey = 1422054725 if self._version in (Version.TD, Version.RA) else 913179935
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

		'MixFSError' is raised if the file is not found.
		"""
		
		inode = self._get_node(name)

		if inode is None:
			raise MixFSError("File not found")

		self._stream.seek(inode.offset)
		return self._stream.read(inode.size)

	# Remove a file from the MIX
	def delete(self, name):
		"""Remove `name` from the MIX

		MixFSError is raised if the file is open or does not exist.
		ValueError is raised if `name` is not valid.
		"""
		
		# We're not using self._get_node() here, because
		# there's no reason in adding a name to a file,
		# that's going to be deleted.
		key = self._get_key(name)
		node = self._index.pop(key, None)
		
		if node is None:
			raise MixFSError(2, name, None, "File not found")
		
		index = self._contents.index(node)
		if index:
			self._contents[index-1].alloc += node.alloc
		del self._contents[index]
	
	# Extract a file to the local filesystem
	def extract(self, name, dest):
		"""Extract `name` to `dest` on the local file system.
		
		Existing files will be overwritten.
		MixFSError is raised if the file is not found.
		ValueError is raised if `name` is not valid.
		"""
		node = self._get_node(name)
		
		if node is None:
			raise MixFSError("File not found")
		
		self._stream.seek(node.offset)
		with open(dest, "wb") as outstream:
			buflen = BLOCKSIZE
			if node.size > buflen:
				buffer = memoryview(bytearray(buflen))
				remaining = node.size
				while remaining >= buflen:
					self._stream.readinto(buffer)
					remaining -= outstream.write(buffer)
				if remaining:
					buffer = buffer[:remaining]
					self._stream.readinto(buffer)
					outstream.write(buffer)
			else:
				buffer = self._stream.read(node.size)
				outstream.write(buffer)
	
	# Insert a new, empty file
	def add_inode(self, name, alloc=4096):
		key = self._get_key(name)
		inode = self._index.get(key)

		if inode is not None:
			if inode.name.startswith("0x"):
				inode.name = name
			raise MixFSError("File exists.")

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
	def insert(self, path: str, name: str) -> None:
		"""Insert 'path' from the local file system as 'name'.

		`MixInternalError` is raised if a file by that name already exists.
		`ValueError` is raised if 'name' is not valid.
		"""
		size = os.stat(source).st_size
		inode = self.allocate(name, size)
		inode.size = size

		blocks, rest = divmod(size, BLOCKSIZE)

		self._stream.seek(inode.offset)
		with open(source, "rb") as InFile:
			if blocks:
				buffer = bytearray(BLOCKSIZE)
				for i in range(blocks):
					InFile.readinto(buffer)
					self._stream.write(buffer)
			if rest:
				buffer = InFile.read(rest)
				self._stream.write(buffer)
	
	# Put a file's contents in a 'bytes' object
	def get_bytes(self, name: str) -> bytes:
		"""!!! STUB !!!"""
		raise NotImplementedError("Stub method")
	
	# Open a file inside the MIX using MixIO
	# Shall work like the built-in open function
	def open(self, name: str, mode: str = "r", buffering: int = -1, encoding: str = None, errors: str = None, newline: str = None):
		"""!!! STUB !!!"""
		raise NotImplementedError("Stub method")
	
	@property
	def has_checksum(self) -> bool:
		"""Define if MIX has a checksum."""
		return bool(self._flags & 1)
	
	@has_checksum.setter
	def has_checksum(self, value: bool) -> None:
		"""Define if MIX has a checksum."""
		if self._version is not Version.TD:
			if value:
				self._flags |= 1
			else:
				self._flags &= -2
	
	@property
	def is_encrypted(self) -> bool:
		"""Define if MIX header is encrypted."""
		return bool(self._flags & 2)
	
	@is_encrypted.setter
	def is_encrypted(self, value: bool) -> None:
		"""Define if MIX header is encrypted."""
		if self._version is not Version.TD:
			if value:
				self._flags |= 2
			else:
				self._flags &= -3


# MixIO instaces are used to work with contained files as if they were real
class MixIO(io.BufferedIOBase):
	"""Access files inside MIXes like files on disk."""
	
	__slots__ = ("_container", "_node", "__cursor", "__readable", "__writable")
	
	def __init__(self, container: MixFile, name: str, flags: int) -> None:
		"""Initialize an abstract stream for `name` on top of `container`."""
		self._container = container
		self._node = container._get_node(name)
		# FIXME: This should probably raise ValueError instead of failing silently on container error
		self.__readable = flags & 1 and container._stream.readable()
		self.__writable = flags & 2 and container._stream.writable()
		self.__cursor = 0
		self._node.links += 1
	
	def readable(self) -> bool:
		# FIXME: Check if we can exchange OSError by MixIOError
		"""Return True if the stream can be read from. If False, read() will raise OSError."""
		if self.closed:
			raise ValueError("I/O operation on closed file")

		return self._container._stream.readable()
	
	def writable(self) -> bool:
		"""Return True if the stream supports writing. If False, write() and truncate() will raise OSError."""
		if self.closed:
			raise ValueError("I/O operation on closed file")

		return self.__writable()
	
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


# Create MIX identifier from name
# Thanks to Olaf van der Spek for providing these functions
def genkey(name: str, version: Version) -> int:
	"""Return the key for `name` according to `version`.

	This is a low-level function that rarely needs to be used directly.
	"""
	n = name.encode(ENCODING, "strict").upper()
	if version is Version.TD or version is Version.RA:
		l = len(n)
		k = 0
		i = 0
		while i < l:
			a = 0
			for j in range(4):
				a >>= 8
				if i < l:
					a |= (n[i] << 24)
					i += 1
			k = (k << 1 | k >> 31) + a & 4294967295
		return k
	if version is Version.TS:
		l = len(n)
		a = l & -4
		if l & 3:
			n += bytes((l - a,))
			n += bytes((n[a],)) * (3 - (l & 3))
		return binascii.crc32(n)
	if version is Version.RG:
		return binascii.crc32(n)
	raise TypeError("`version` must be a Version enumeration member.")
