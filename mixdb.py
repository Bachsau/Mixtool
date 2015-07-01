#!/usr/bin/python3
# coding=utf8

import sqlite3 as SQLite3

from mixlib import genkey

# Constants
TYPES = "td", "ts"

# A global MIX Database interface
class MixDB:
	def __init__(self, dbfile=':memory:'):
		self.__closed = False
		
		self.DB = SQLite3.connect(dbfile)
		self.DBQuery = self.DB.cursor()
		
		self.DBQuery.execute("PRAGMA encoding = 'UTF-8';")
		
		try:
			for type_ in TYPES:
				self.DBQuery.execute("CREATE TABLE IF NOT EXISTS `mixdb_{0}` (`key_{0}` INT PRIMARY KEY NOT NULL CHECK(TYPEOF(`key_{0}`) = 'integer'), `name` CHAR NOT NULL CHECK(TYPEOF(`name`) = 'text')) WITHOUT ROWID;".format(type_))
		except SQLite3.Error as e:
			self.DB.rollback()
			raise MixDBError("SQLite3:", e.args[0])
		else:
			self.DB.commit()
			
	def __del__(self):
		self.close()
		
	def submit(type_, data):
		pass
		
	def retrieve(type_, keys):
			
	def close(self):
		if not self.__closed:
			self.DBQuery.close()
			self.DBQuery = None
			self.DB.commit()
			self.DB.close()
			self.DB = None
			self.__closed = True
		
class MixDBError(Exception):
	pass
		
			
MixDB()
