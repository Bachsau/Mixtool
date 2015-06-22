#!/usr/bin/python3
# coding=utf8
open = None

# AbstractIO expands the standard IO module with Classes to work on
# abstract file-in-file objects with infinite recursion.
#
# Designed to work with the MixLib it should work with every other class
# that resembles its interface.

import io as IO
import os as OS

# Works on a MixFile instance to represent a single file inside it
# inherits from IO.IOBase and implements IO.RawIOBase.
class AbstractIO(IO.IOBase):
	def __init__(self, parent, inode, mode):
		# References to MixFile instance and IO stream
		self.MixFile = parent
		self.Stream  = parent.Stream
		self.inode   = inode
		
		# Relative abstracted data
		self.position = 0
		
	# Closing a file removes all references to the MixFile instance,
	# so its destructor may be called
	def close(self):
		self.MixFile = None
		self.Stream  = None
		self.closed  = True
		
	def seek(self, offset, whence = OS.SEEK_SET):
		# Calculate the real offset from an abstract one
		if whence == OS.SEEK_SET:
			newposition = self.offset + offset
		elif whence == OS.SEEK_CUR:
			newposition = self.realposition + offset
		else:
			newposition = self.end + offset
			
		# Check if we're out of bounds and corret it
		if newposition < self.offset:
			newposition = self.offset
		elif newposition > self.end:
			newposition = self.end
			
		# Save position to instance and return.
		self.realposition = newposition
		self.position     = newposition - self.offset
		return self.position
		
	def tell(self):
		return self.position
		
	def seekable(self):
		return True
		
	def read(self, size = -1):
		# Readall and never beyond EOF
		if size == -1 or self.position + size > self.size:
			size = self.size - self.position
			
		# Now we do real file access
		self.Stream.seek(self.realposition, OS.SEEK_SET)
		data = self.Stream.read(size)
		
		# Save position to instance and return.
		self.realposition = self.Stream.tell()
		self.position     = self.realposition - self.offset
		return self.position
			
	def readall(self):
		return self.read(-1)
		
	
	
class AbstractIOError(Exception):
	# Error Class
	pass
	
# Implements the build-in open function.
# Uses MixLib.open (or other file-in-files open function) as the opener
# Return a corresponding AbstractIO-derived instance
def open(filename, backend, mode="r", buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
	if opener is None:
		opener == backend._opener()
		
		
