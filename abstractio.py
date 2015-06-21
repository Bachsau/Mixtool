#!/usr/bin/python3
# coding=utf8

import io as IO
import os as OS

# Works on a MixFile instance to represent a single file inside it
# Should inherit from IO.IOBase and implement IO.IOBase.
class AbstractIO(IO.BaseIO):
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
	
# Implement OS.open()
# http://docs.python.org/3/library/os.html#os.open
def open(parent, inode, flags, mode=0o777):
	pass
