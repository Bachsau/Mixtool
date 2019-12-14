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

__all__ = [
	"SQLiteDB",
	"NamesDB"
]
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
		self.query.close()
		self.query = None
		sqlite3.Connection.close(self)
	
	def cursor(self):
		"""Return the cursor."""
		return self.query


# A global MIX Database interface
class NamesDB(object):
	"""Mixtool’s names database"""
	
	__slots__ = ("_db",)
	
	def __init__(self, data_path: str):
		"""Create or open the database file."""
		dbfile = os.sep.join((data_path, "names.db"))
		# SQLite:
		# 'keyword'    A keyword in single quotes is a string literal.
		# "keyword"    A keyword in double-quotes is an identifier.
		
		for attempt in range(2):
			if attempt:
				bakfile = dbfile + ".bak"
				# No error handling here. It fails on second attempt.
				if not os.path.exists(bakfile):
					os.rename(dbfile, bakfile)
				else:
					os.remove(dbfile)
			try:
				self._db = SQLiteDB(dbfile, isolation_level=None, check_same_thread=False)
			except sqlite3.OperationalError:
				if attempt:
					raise
				continue  # Something's foul. Discard db and start over.
			else:
				self._db.query.execute("PRAGMA locking_mode = EXCLUSIVE;")
				self._db.query.execute("PRAGMA journal_mode = TRUNCATE;")
				self._db.query.execute("PRAGMA synchronous = FULL;")
				try:
					self._db.query.execute("SELECT COUNT(*) FROM \"sqlite_master\" WHERE \"name\" NOT GLOB 'sqlite_*'")
				except sqlite3.OperationalError:
					if attempt:
						raise
					continue  # Something's foul. Discard db and start over.
				else:
					if self._db.query.fetchone()[0]:
						# TODO: Check meta table
						pass
					else:
						self._db.query.execute("CREATE TABLE \"meta\" (\"property\" CHAR PRIMARY KEY NOT NULL, \"value\" CHAR NOT NULL) WITHOUT ROWID;")
						self._db.query.execute("CREATE TABLE \"names_lo\" (\"key\" INT PRIMARY KEY NOT NULL, \"name\" CHAR NOT NULL) WITHOUT ROWID;")
						self._db.query.execute("CREATE TABLE \"names_hi\" (\"key\" INT PRIMARY KEY NOT NULL, \"name\" CHAR NOT NULL) WITHOUT ROWID;")
						self._db.query.executemany("INSERT INTO \"meta\" VALUES (?, ?);", (
							("vendor", "Bachsau"),
							("product", "Mixtool"),
							("purpose", "names"),
							("schema", "0")
						))
			break
	
	def submit(version: int, names):
		pass
	
	def retrieve(version: int, keys):
		pass
	
	# To get instid for comparison
	def query_instid() -> uuid.UUID:
		# Moved here from __main__.py
		# (needs rework)
		try:
			inst_id = uuid.UUID(int=self.settings["instid"])
		except ValueError:
			inst_id = None
		if inst_id is not None\
		and inst_id.variant == uuid.RFC_4122\
		and inst_id.version == 4:
			self.inst_id = inst_id
		else:
			inst_id = uuid.uuid4()
			self.settings["instid"] = inst_id.int
			if self._save_settings():
				self.inst_id = inst_id
	
	def close(self):
		if self._db is not None:
			self._db.close()
			self._db = None
