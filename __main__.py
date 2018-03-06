#!/usr/bin/env python3
# coding=utf8

# Copyright (C) 2015-2018 Bachsau
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

"""Mixtool GTK+ 3 application"""
import sys
import os
import signal

# Modules for platform-specific configuration
if sys.platform.startswith('win'):
	import winreg
	_PLATFORM = 1
elif sys.platform.startswith('darwin'):
	import plistlib
	_PLATFORM = 2
else:
	import configparser
	_PLATFORM = 0

# GTK+ 3 modules
import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gio, Gdk, Gtk

# Local modules
import mixlib

# Constants
COLUMN_ROWID    = 0
COLUMN_NAME     = 1
COLUMN_OFFSET   = 2
COLUMN_SIZE     = 3
COLUMN_OVERHEAD = 4

# The settings manager is responsible for saving and retrieving
# the user's settings according to the platform it runs on
class Configuration(object):
	"""Save and Retrieve settings based on platform standards.
	
	This class's constructor automatically returns a subclass
	specific to the current platform.
	
	On Windows, settings are saved to the Registry.
	On macOS, they are saved in property lists.
	On all other platforms, plain-text configuration files are used.
	"""
	
	__slots__ = ()
	
	def __new__(cls, *args, **kwargs):
		"""Return a platform-specific subclass of 'Configuration'.
		
		Falls back to default when inherited by a subclass.
		"""
		
		if cls.__base__ is object:
			if _PLATFORM == 1:
				return ConfigWin.__new__(ConfigWin, *args, **kwargs)
			elif _PLATFORM == 2:
				return ConfigMac.__new__(ConfigMac, *args, **kwargs)
			else:
				return ConfigGen.__new__(ConfigGen, *args, **kwargs)
		else:
			return object.__new__(cls, *args, **kwargs)
	
	def __init__(self):
		"""Initialize the settings manager."""
			
	def register(self, name: str, default):
		"""Register a setting to be handled.
		
		The setting is identified by 'name' with 'default' beeing its initial value.
		Its type is considered the type for the setting, which can not be changed later on.
		Acceptable types are 'str', 'bytes', 'bytearray', 'int', 'float' and 'bool'.
		'bytearray' objects are saved as 'bytes'. 'TypeError' is raised for inacceptable types.
		"""

class ConfigWin(Configuration):
	"""Save and Retrieve settings using the Registry."""
	
	__slots__ = ()
	
class ConfigMac(Configuration):
	"""Save and Retrieve settings using a property list."""
	
	__slots__ = ()
	
class ConfigGen(Configuration):
	"""Save and Retrieve settings using a configuration file."""
	
	__slots__ = ()


class Configuration_OLD(object):
	"""General settings manager"""
	
	# In alpha we will be using an ini-file on all platforms
	# FIXME: Use plist on macOS and the registry on Windows
	def __init__(self, defaults):
		"""Initialize the settings manager with default settings"""
		
		# Determine data directories
		home_dir = os.path.expanduser("~")
		
		if home_dir == "~":
			home_dir = os.path.dirname(os.path.realpath(__file__))
		else:
			home_dir = os.path.realpath(home_dir)
		
		if sys.platform.startswith('win'):
			# Microsoft Windows
			data_dir = os.environ.get("LOCALAPPDATA")

			if data_dir is None:
				data_dir = home_dir + "\\AppData\\Local\\Bachsau\\Mixtool"
			else:
				data_dir = os.path.realpath(data_dir) + "\\Bachsau\\Mixtool"

			config_dir = os.environ.get("APPDATA")

			if config_dir is None:
				config_dir = home_dir + "\\AppData\\Roaming\\Bachsau\\Mixtool"
			else:
				config_dir = os.path.realpath(config_dir) + "\\Bachsau\\Mixtool"

		elif sys.platform.startswith('darwin'):
			# Apple macOS
			data_dir = home_dir + "/Library/Application Support/com.bachsau.mixtool"
			config_dir = home_dir + "/Library/Preferences/com.bachsau.mixtool"

		else:
			# Linux and others
			data_dir = os.environ.get("XDG_DATA_HOME")

			if data_dir is None:
				data_dir = home_dir + "/.local/share/bachsau/mixtool"
			else:
				data_dir = os.path.realpath(data_dir) + "/bachsau/mixtool"

			config_dir = os.environ.get("XDG_CONFIG_HOME")

			if config_dir is None:
				config_dir = home_dir + "/.config/bachsau/mixtool"
			else:
				config_dir = os.path.realpath(config_dir) + "/bachsau/mixtool"

		# Create non-existent directories
		try:
			if not os.path.isdir(data_dir):
				os.makedirs(data_dir)

			if not os.path.isdir(config_dir):
				os.makedirs(config_dir)
		except OSError:
			messagebox("Unable to create data directories! Your settings will not be saved.", "e")
		
		# Read configuration file
		# FIXME: Could be a class with implicit setting and write method
		settings = configparser.ConfigParser(None, dict, False, delimiters=("=",), comment_prefixes=(";",), inline_comment_prefixes=None, strict=True, empty_lines_in_values=False, default_section=None, interpolation=None)
		settings.optionxform = str.title
		settings.read_dict({"Mixtool": defaults})
		
		config_file = os.sep.join((config_dir, "settings.ini"))
		
		try:
			stream = open(config_file, encoding="utf_8")
		except FileNotFoundError:
			pass
		except OSError:
			messagebox("Error reading configuration file.", "e")
		else:
			settings.read_file(stream)
			stream.close()
		
		# Populate object
		self.data_dir = data_dir
		self.config_dir = config_dir
		self.config_file = config_file
		self.settings = settings
		

# The application controller
class Mixtool(Gtk.Application):
	"""Application management class"""
	__slots__ = "app_dir", "settings"
	
	# Object initializer
	def __init__(self, application_id, flags):
		"""Initialize GTK+ Application"""
		Gtk.Application.__init__(self, application_id=application_id, flags=flags)
		self.app_dir = os.path.dirname(os.path.realpath(__file__))
		
	# This is run when Gio.Application initializes the first instance.
	# It is not run on any remote controllers.
	def do_startup(self):
		"""Initialize the main instance"""
		Gtk.Application.do_startup(self)
		
		# Default settings, as saved in the configuration file
		default_settings = {
			"Simplenames": "Yes",
			"Insertlower": "Yes",
			"Decrypt": "Yes",
			"Backup": "Yes"
		}
		
		#self.settings = Configuration_OLD(default_settings)
		
		
	# Method that creates a new main window in the main instance.
	# Can be run multiple times on behalf of remote controllers.
	def do_activate(self, *args):
		"""Create a new main window"""
		MainWindow(self)
		
	def save_config(self):
		"""Save configuration to file"""
		try:
			stream = open(self.config_file, "w", encoding="utf_8")
		except OSError:
			messagebox("Error writing configuration file.", "e")
		else:
			self.settings.write(stream, False)
			stream.close()
		
class MainWindow(object):
	"Main-Window controller class"
	def __init__(self, application):
		self.Application = application

		# Read GUI from file and retrieve objects from GtkBuilder
		try:
			GtkBuilder = Gtk.Builder()
			GtkBuilder.add_from_file("gui.glade")
		except GObject.GError:
			messagebox("Error reading GUI file", "e")
			raise
		else:
			GtkBuilder.connect_signals(self)

		self.GtkBuilder          = GtkBuilder
		self.MainWindow          = GtkBuilder.get_object("MainWindow")
		self.OpenDialog          = GtkBuilder.get_object("OpenDialog")
		self.SaveDialog          = GtkBuilder.get_object("SaveDialog")
		self.ExtractSingleDialog = GtkBuilder.get_object("ExtractSingleDialog")
		self.ExtractMultiDialog  = GtkBuilder.get_object("ExtractMultiDialog")
		self.InsertDialog        = GtkBuilder.get_object("InsertDialog")
		self.SearchDialog        = GtkBuilder.get_object("SearchDialog")
		self.SearchDialogEntry   = GtkBuilder.get_object("SearchDialogEntry")
		self.AboutDialog         = GtkBuilder.get_object("AboutDialog")
		self.SettingsDialog      = GtkBuilder.get_object("SettingsDialog")
		self.PropertiesDialog    = GtkBuilder.get_object("PropertiesDialog")
		self.ContentList         = GtkBuilder.get_object("ContentList")
		self.ContentStore        = GtkBuilder.get_object("ContentStore")
		self.ContentSelector     = GtkBuilder.get_object("ContentSelector")
		self.StatusBar           = GtkBuilder.get_object("StatusBar")

		# Initially sort by Offset
		self.ContentStore.set_sort_column_id(COLUMN_OFFSET, Gtk.SortType.ASCENDING)

		# Fire up the main window
		self.MainWindow.set_application(application)
		self.MainWindow.show()

		self.reset()

	# Reset GUI and close file
	def reset(self, *args):
		self.MixFile   = None
		self.filename  = "Untitled"
		self.contents  = {}
		self.ContentStore.clear()
		self.set_titlebar(self.filename)
		self.set_statusbar("This is alpha software. Use at your own risk!")
		
	def optimize(self, *args):
		self.MixFile.write_index(True)
		self.refresh()

	# Load file
	def loadfile(self, filename):
		# TODO: Input sanitising, test for existence
		try:
			self.MixFile = mixlib.MixFile(open(filename, "r+b"))
		except Exception as error:
			messagebox("Error loading MIX file" ,"e", self.MainWindow)
			raise

		self.filename = os.path.basename(filename)
		self.mixtype = ("TD", "RA", "TS")[self.MixFile.get_mixtype()]

		self.set_titlebar(self.filename)
		self.set_statusbar(" ".join((self.mixtype, "MIX contains", str(self.MixFile.get_filecount()), "files.")))

		self.refresh()
			
	def refresh(self):
		self.contents  = {}
		self.ContentStore.clear()
		
		for inode in self.MixFile.get_contents(True):
			# TODO: Stop using private methods
			# 3rd party developers: Do NOT use MixFile._get_inode()!
			# There will be better ways to identify a file.
			rowid = id(self.MixFile._get_inode(inode[0]))
			treeiter = self.ContentStore.append((
				rowid,
				inode[0], # Name
				inode[2], # Offset
				inode[1], # Size
				inode[3] - inode[1] # Alloc - Size = Overhead
			))
			self.contents[rowid] = (treeiter, inode)

	# Delete file(s) from mix
	def delete_selected(self, *args):
		pass

	# Dialog functions
	def opendialog(self, *args):
		response = self.OpenDialog.run()
		self.OpenDialog.hide()
		if response == Gtk.ResponseType.OK:
			self.loadfile(self.OpenDialog.get_filename())
			
	# Insert dialog
	def insertdialog(self, *args):
		if self.MixFile is not None:
			response = self.InsertDialog.run()
			self.InsertDialog.hide()
			
			if response == Gtk.ResponseType.OK:
				inpath = self.InsertDialog.get_filename()
				filename = os.path.basename(inpath)
				inode = self.MixFile.insert(filename, inpath)
				
				self.MixFile.write_index()
				self.refresh()


	def extractdialog(self, *args):
		rows = self.get_selected_rows()
		count = len(rows)

		if count == 0:
			messagebox("Nothing selected", "e", self.MainWindow)
		else:
			if count > 1:
				Dialog = self.ExtractMultiDialog
				Dialog.set_current_name(self.filename.replace(".", "_"))
			else:
				filename = rows[0][COLUMN_NAME]
				Dialog = self.ExtractSingleDialog
				Dialog.set_current_name(filename)

			response = Dialog.run()
			Dialog.hide()

			if response == Gtk.ResponseType.OK:
				outpath = Dialog.get_filename()

				if count > 1:
					# Mitigate FileChoserDialog's inconsistent behavior
					# to protect user's files
					if os.listdir(outpath):
						outpath = os.path.join(outpath, Dialog.get_current_name())
						os.mkdir(outpath)

					# Save every file with its original name
					for row in rows:
						filename = row[COLUMN_NAME]
						self.MixFile.extract(filename, os.path.join(outpath, filename))
				else:
					self.MixFile.extract(filename, outpath)

	def get_selected_rows(self):
		rows = []
		for path in self.ContentSelector.get_selected_rows()[1]:
			rows.append(self.ContentStore[path])
		return rows

	def propertiesdialog(self, *args):
		self.PropertiesDialog.run()
		self.PropertiesDialog.hide()

	def settingsdialog(self, *args):
		self.SettingsDialog.run()
		self.SettingsDialog.hide()

	def aboutdialog(self, *args):
		self.AboutDialog.run()
		self.AboutDialog.hide()

	# Search current file for names
	# TODO: Implement wildcard searching
	def searchdialog(self, *args):
		if self.MixFile is not None:
			self.SearchDialogEntry.grab_focus()
			self.SearchDialogEntry.select_region(0, -1)
			response = self.SearchDialog.run()
			self.SearchDialog.hide()
			search = self.SearchDialogEntry.get_text()

			if response == Gtk.ResponseType.OK  and search:
				name  = self.SearchDialogEntry.get_text()
				# TODO: Stop using private methods
				# 3rd party developers: Do NOT use MixFile._get_inode()!
				# There will be better ways to identify a file.
				inode = self.MixFile._get_inode(name)

				if inode is not None:
					treeiter = self.contents[id(inode)][0]
					self.ContentStore[treeiter][COLUMN_NAME] = inode.name

					path = self.ContentStore.get_path(treeiter)
					self.ContentList.set_cursor(path)
				else:
					messagebox("Found no file matching \"" + name + "\" in current mix", "i", self.MainWindow)
		else:
			messagebox("Search needs an open MIX file", "e", self.MainWindow)

	def set_statusbar(self, text):
		self.StatusBar.set_text(str(text))

	def set_titlebar(self, text):
		self.MainWindow.set_title(text + " – Mixtool (Alpha)")

	# Close window
	# Gtk.Application quits if this was the last one
	def close(self, *args):
		# Cleanup GtkBuilder
		for obj in self.GtkBuilder.get_objects():
			try:
				obj.destroy()
			except AttributeError:
				pass
		
		
# Starter
def main():
	# Since GTK+ does not support KeyboardInterrupt, reset SIGINT to default.
	# TODO: Find and implement a better way to handle this
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	
	# Initialize GObject's treads capability
	GObject.threads_init()
	
	# Initialize GTK Application
	GObject.set_application_name("Mixtool")
	application = Mixtool("com.bachsau.mixtool", Gio.ApplicationFlags.NON_UNIQUE)
	
	# Start GUI
	# FIXME: All exceptions raised from inside are caught by GTK!
	#        We need to look for a deeper place to catch them all.
	status = application.run()
	print("GTK returned.", file=sys.stderr)
	
	return status

# A simple, instance-independent messagebox
# TODO: Add Traceback-Textbox
# TODO: Center on screen if it lacks a parent (if possible)
def messagebox(text, type_="i", parent=None):
	if type_ == "e":
		message_type = Gtk.MessageType.ERROR
		buttons_type = Gtk.ButtonsType.OK
	else:
		message_type = Gtk.MessageType.INFO
		buttons_type = Gtk.ButtonsType.OK

	dialog = Gtk.MessageDialog(parent, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, message_type, buttons_type, str(text))
	response = dialog.run()
	dialog.destroy()
	return response

# Run the application
sys.exit(main())
