#!/usr/bin/env python3
# coding=utf_8

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
import configparser

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


# Main application controller
class Mixtool(Gtk.Application):
	"""Application management class"""
	
	__slots__ = ("home_dir", "data_dir", "config_file", "settings", "gui", "window")
	
	# Object initializer
	def __init__(self) -> None:
		"""Initialize the Mixtool instance"""
		Gtk.Application.__init__(self, application_id="com.bachsau.mixtool")
		
		self.window = None
	
	# This is run when Gtk.Application initializes the first instance.
	# It is not run on any remote controllers.
	def do_startup(self) -> None:
		"""Initialize the main instance"""
		Gtk.Application.do_startup(self)
		
		# Determine a platform-specific data directory
		self.home_dir = os.path.realpath(os.path.expanduser("~"))
		
		if sys.platform.startswith('win'):
			# Microsoft Windows
			os_appdata = os.environ.get("APPDATA")
			
			if os_appdata is None:
				self.data_dir = self.home_dir + "\\AppData\\Roaming\\Bachsau\\Mixtool"
			else:
				self.data_dir = os.path.realpath(os_appdata) + "\\Bachsau\\Mixtool"
		
		elif sys.platform.startswith('darwin'):
			# Apple macOS
			self.data_dir = self.home_dir + "/Library/Application Support/Bachsau/Mixtool"
		
		else:
			# Linux and others
			os_appdata = os.environ.get("XDG_DATA_HOME")
			
			if os_appdata is None:
				self.data_dir = self.home_dir + "/.local/share/bachsau/mixtool"
			else:
				self.data_dir = os.path.realpath(os_appdata) + "/bachsau/mixtool"
		
		# Create non-existent directories
		try:
			if not os.path.isdir(self.data_dir):
				os.makedirs(self.data_dir)
		except OSError:
			messagebox("Unable to create data directory:\n{0}\n\nYour settings will not be saved.".format(self.data_dir), "e")
		
		# Set location of configuration file
		self.config_file = os.sep.join((self.data_dir, "settings.ini"))
		
		# Default settings, as saved in the configuration file
		default_settings = {
			"Simplenames": "Yes",
			"Insertlower": "Yes",
			"Decrypt": "Yes",
			"Backup": "Yes"
		}
		
		# Initialize ConfigParser
		self.settings = configparser.ConfigParser(None, dict, False, delimiters=("=",), comment_prefixes=(";",), inline_comment_prefixes=(";",), strict=True, empty_lines_in_values=False, default_section=None, interpolation=None)
		self.settings.optionxform = str.title
		self.settings.read_dict({"Mixtool": default_settings})
		
		# Parse configuration file
		try:
			config_stream = open(self.config_file, encoding="ascii")
		except FileNotFoundError:
			pass
		except OSError:
			messagebox("Error reading configuration file.", "e")
		else:
			# FIXME: Add message boxes for parsing errors
			self.settings.read_file(config_stream)
			config_stream.close()
		
		# Parse GUI file
		try:
			self.gui = Gtk.Builder.new_from_file("gui.glade")
		except GObject.GError:
			messagebox("Error parsing GUI file", "e")
		else:
			legacy_controller = OldWindowController(self)
			self.gui.connect_signals(legacy_controller)
	
	# Method that creates a main window in the first instance.
	# Can be run multiple times on behalf of remote controllers.
	def do_activate(self) -> None:
		"""Create a new main window or present an existing one."""
		# FIXME: Edit multiple files in tabs
		if self.window is None:
			self.window = self.gui.get_object("MainWindow")
			self.add_window(self.window)
			self.window.show()
		else:
			self.window.present()
			print("Activated main window on behalf of remote controller.", file=sys.stderr)
	
	def do_save_settings(self) -> None:
		"""Save configuration to file"""
		try:
			config_stream = open(self.config_file, "w", encoding="ascii")
		except OSError:
			messagebox("Error writing configuration file.", "e")
		else:
			self.settings.write(config_stream, True)
			config_stream.close()


# <old_code>
		
class OldWindowController(object):
	"Main-Window controller class"
	def __init__(self, application):
		# Read GUI from file and retrieve objects from GtkBuilder
		GtkBuilder = application.gui
#		try:
#			GtkBuilder = Gtk.Builder()
#			GtkBuilder.add_from_file("gui.glade")
#		except GObject.GError:
#			messagebox("Error reading GUI file", "e")
#			raise
#		else:
#			GtkBuilder.connect_signals(self)

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
#		self.MainWindow.set_application(application)
#		self.MainWindow.show()

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
				
# </old_code>


# Starter
def main() -> int:
	"""Run the Mixtool application and return a status code."""
	# Since GTK+ does not support KeyboardInterrupt, reset SIGINT to default.
	# TODO: Find and implement a better way to handle this.
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	
	# Initialize GObject's treads capability
	GObject.threads_init()
	
	# Initialize GTK Application
	GObject.set_application_name("Mixtool")
	application = Mixtool()
	
	# Start GUI
	# FIXME: All exceptions raised from inside are caught by GTK!
	#        I need to look for a deeper place to catch them all.
	status = application.run()
	print("GTK returned.", file=sys.stderr)
	
	return status

# A simple, instance-independent messagebox
def messagebox(text: str, type_: str = "i", parent: Gtk.Window = None, *, secondary: str = None) -> None:
	"""Display a dialog box containing `text` and an OK button.
	
	`type_` can be 'i' for infomation, 'e' for error or 'w' for warning.
	
	If `parent` is given, the dialog will be a child of that window and
	centered upon it.
	
	`secondary` can be used to display additional text. The primary text will
	appear bolder in that case.
	"""
	if type_ == "i":
		message_type = Gtk.MessageType.INFO
	if type_ == "e":
		message_type = Gtk.MessageType.ERROR
	elif type_ == "w":
		message_type = Gtk.MessageType.WARNING
	else:
		raise ValueError("Invalid message type.")
	
	if parent is None:
		flags = Gtk.DialogFlags(0)
		position = Gtk.WindowPosition.CENTER
	else:
		flags = Gtk.DialogFlags.DESTROY_WITH_PARENT
		position = Gtk.WindowPosition.CENTER_ON_PARENT
	
	dialog = Gtk.MessageDialog(parent, flags, message_type, Gtk.ButtonsType.OK, str(text))
	dialog.set_position(position)
	
	if secondary is not None:
		dialog.format_secondary_text(str(secondary))
	
	dialog.run()
	dialog.destroy()


# Run the application
sys.exit(main())
