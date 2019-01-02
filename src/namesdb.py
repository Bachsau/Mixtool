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

"""Mixtool’s names database module"""

__version__ = "0.2.0-volatile"
__author__ = "Bachsau"

# Standard modules
import os
import sqlite3
import uuid


class SQLiteDB(sqlite3.Connection):
	"""An SQLite3 connection with implicit cursor."""
	
	__slots__ = ("query",)
	
	def __init__(self, *args, **kwargs):
		"""Connect to an SQLite3 database file."""
		sqlite3.Connection.__init__(self, *args, **kwargs)
		self.query = sqlite3.Connection.cursor(self)
	
	def close(self):
		"""Close the connection."""
		self.query = None
		sqlite3.Connection.close(self)
	
	def cursor(self):
		"""Return the cursor."""
		return self.query


# A global MIX Database interface
class NamesDB(object):
	"""Mixtool’s names database"""
	
	__slots__ = ("_db",)
	
	def __init__(self, data_path: str, inst_id: uuid.UUID):
		"""Create or open the database file."""
		# SQLite:
		# 'keyword'    A keyword in single quotes is a string literal.
		# "keyword"    A keyword in double-quotes is an identifier.
		dbfile = os.sep.join((data_path, "cache.db"))
		self._db = SQLiteDB(dbfile, isolation_level=None, check_same_thread=False)
		self._db.query.execute("PRAGMA journal_mode = TRUNCATE;")
		self._db.query.execute("PRAGMA synchronous = NORMAL;")
		
		self._db.query.execute("CREATE TABLE IF NOT EXISTS \"names_v1\" (\"key\" INT PRIMARY KEY NOT NULL, \"name\" CHAR NOT NULL) WITHOUT ROWID;")
		self._db.query.execute("CREATE TABLE IF NOT EXISTS \"names_v3\" (\"key\" INT PRIMARY KEY NOT NULL, \"name\" CHAR NOT NULL) WITHOUT ROWID;")
		self._db.query.execute("CREATE TABLE IF NOT EXISTS \"store\" (\"option\" CHAR PRIMARY KEY NOT NULL, \"value\" INT NOT NULL) WITHOUT ROWID;")
	
	def submit(version: int, names):
		pass
	
	def retrieve(version: int, keys):
		pass
	
	def close(self):
		if self._db is not None:
			self._db.close()
			self._db = None
