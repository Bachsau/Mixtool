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

"""Mixtool GTK+ 3 application"""

__version__ = "0.2.0-volatile"

# Standard modules
import sys
import os
import signal
import collections
import configparser
from urllib import parse

# Third party modules
import gi
gi.require_version("Pango", "1.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, GObject, Gio, Pango, Gtk

# Local modules
import mixlib

# Constants
COLUMN_ROWID    = -1
COLUMN_NAME     = 0
COLUMN_OFFSET   = 1
COLUMN_SIZE     = 2
COLUMN_OVERHEAD = 3


# FileRecord data type
_FileRecord = collections.namedtuple("_FileRecord", ("path", "stream", "container", "store", "button"))

# Main application controller
class Mixtool(Gtk.Application):
	"""Application management class"""
	
	# The GtkFileFilter used by open/save dialogs
	file_filter = Gtk.FileFilter()
	file_filter.set_name("MIX files")
	file_filter.add_pattern("*.mix")
	file_filter.add_pattern("*.MIX")
	
	# Object initializer
	def __init__(self) -> None:
		"""Initialize the Mixtool instance"""
		Gtk.Application.__init__(self, application_id="com.bachsau.mixtool", flags=Gio.ApplicationFlags.HANDLES_OPEN)
		
		# Initialize attributes
		self.home_dir = None
		self.data_dir = None
		self.config_file = None
		self.settings = None
		self.gtk_builder = None
		self.window = None
		self.files = []
		current_file = None
	
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
			messagebox("Unable to create data directory:\n{0}\n\nYour settings will not be saved.".format(self.data_dir), "w")
		
		# Set location of configuration file
		self.config_file = os.sep.join((self.data_dir, "settings.ini"))
		
		# Default settings, as saved in the configuration file
		default_settings = {
			"simplenames": "yes",
			"insertlower": "yes",
			"decrypt": "yes",
			"backup": "no",
			"lastdir": parse.quote(self.home_dir)
		}
		
		# Initialize ConfigParser
		self.settings = configparser.ConfigParser(None, dict, False, delimiters=("=",), comment_prefixes=(";",), inline_comment_prefixes=(";",), strict=True, empty_lines_in_values=False, default_section=None, interpolation=None)
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
		gui_file = os.sep.join((os.path.dirname(os.path.realpath(__file__)), "gui.glade"))
		self.gtk_builder = Gtk.Builder.new_from_file(gui_file)

		global legacy_controller
		legacy_controller = OldWindowController(self)
		callback_map = {
			"quit_application": legacy_controller.close,
			"invoke_new_dialog": legacy_controller.reset,
			"invoke_open_dialog": self.invoke_open_dialog,
			"optimize_mixfile": legacy_controller.optimize,
			"invoke_insert_dialog": legacy_controller.insertdialog,
			"delete_selected": legacy_controller.delete_selected,
			"invoke_extract_dialog": legacy_controller.extractdialog,
			"invoke_search_dialog": legacy_controller.searchdialog,
			"invoke_properties_dialog": legacy_controller.propertiesdialog,
			"invoke_settings_dialog": legacy_controller.settingsdialog,
			"invoke_about_dialog": self.invoke_about_dialog,
			"invoke_extract_dialog": legacy_controller.extractdialog,
			"show_donate_uri": self.show_donate_uri,
			"close_current_file": self.close_current_file
		}
		self.gtk_builder.connect_signals(callback_map)
	
	# Close file in current tab
	def close_current_file(self, widget: Gtk.Widget) -> bool:
		"""Close the currently active file."""
		file = self.current_file
		
		# Remove from list of open files
		self.files.remove(file)
		
		# Close stream
		file.stream.close()
		
		# Remove the tab
		file.button.destroy()
		
		if self.files:
			# Activate previous tab
			self.files[-1].button.set_active(True)
		else:
			# Remove current_file
			self.current_file = None
			self.gtk_builder.get_object("ContentList").set_model(None)
			
			# Switch to Quit button and disable ContentList
			self.gtk_builder.get_object("Toolbar.Close").hide()
			self.gtk_builder.get_object("Toolbar.Quit").show()
			self.gtk_builder.get_object("ContentList").set_sensitive(False)
		
		return True
	
	# Show about dialog
	def invoke_about_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a dialog with information on Mixtool."""
		dialog = self.gtk_builder.get_object("AboutDialog")
		dialog.set_default_response(Gtk.ResponseType.DELETE_EVENT)
		dialog.run()
		dialog.hide()
		return True
	
	# Open donation website in default browser
	def show_donate_uri(self, widget: Gtk.Widget) -> bool:
		"""Open donation website in default browser."""
		Gtk.show_uri_on_window(widget.get_toplevel(), "http://go.bachsau.com/mtdonate", Gtk.get_current_event_time())
		return True
	
	# Callback to open files by using a dialog
	def invoke_open_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a file chooser dialog and open selected files."""
		lastdir = parse.unquote(self.settings["Mixtool"]["lastdir"])
		dialog = Gtk.FileChooserNative.new("Open MIX file", self.window, Gtk.FileChooserAction.OPEN, "_Open", "_Cancel")
		dialog.set_modal(True)
		dialog.set_select_multiple(True)
		dialog.add_filter(self.file_filter)
		dialog.set_filter(self.file_filter)
		dialog.set_current_folder(lastdir)
		response = dialog.run()
		
		if response == Gtk.ResponseType.ACCEPT:
			self.mark_busy()
			
			# Save lastdir
			newdir = dialog.get_current_folder()
			if newdir != lastdir:
				self.settings["Mixtool"]["lastdir"] = parse.quote(newdir)
				self.save_settings()
			
			# Open the files
			for path in dialog.get_filenames():
				button = self.open_file(path)
			
			# Switch to last opened file
			if isinstance(button, Gtk.RadioButton):
				button.toggled() if button.get_active() else button.set_active(True)
			
				# Switch to Close button and enable ContentList
				self.gtk_builder.get_object("Toolbar.Quit").hide()
				self.gtk_builder.get_object("Toolbar.Close").show()
				self.gtk_builder.get_object("ContentList").set_sensitive(True)
			
			self.unmark_busy()
		
		dialog.destroy()
		return True
	
	def open_file(self, path: str) -> Gtk.RadioButton:
		"""Try to open the file at `path` and return the corresponding `Gtk.RadioButton`."""
		path = os.path.realpath(path)
		
		# Check if file is already open
		for already_open in self.files:
			if os.path.samefile(already_open.path, path):
				messagebox("This file is already open and can only be opened once:", "e", self.window, secondary=path)
				return None
		
		try:
			# TODO: Catch errors from mixlib.MixFile separately,
			# so stream can be closed cleanly
			stream = open(path, "r+b")
			container = mixlib.MixFile(stream)
		except Exception:
			messagebox("Error loading MIX file:" ,"e", self.window, secondary=path)
		else:
			# Initialize a Gtk.ListStore
			store = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_UINT, GObject.TYPE_UINT, GObject.TYPE_UINT)
			store.set_sort_column_id(0, Gtk.SortType.ASCENDING)
			for record in container.get_contents(True):
				store.append((
					record[0], # Name
					record[2], # Offset
					record[1], # Size
					record[3] - record[1] # Alloc - Size = Overhead
				))
			
			# Add a button
			button = Gtk.RadioButton.new_with_label_from_widget(already_open.button if self.files else None, os.path.basename(path))
			button.set_mode(False)
			button.get_child().set_ellipsize(Pango.EllipsizeMode.END)
			button.set_tooltip_text(path)
			self.gtk_builder.get_object("TabBar").pack_start(button, True, True, 0)
			button.show()
			
			# Create the file record
			file = _FileRecord(path, stream, container, store, button)
			self.files.append(file)
			
			# Connect the signal
			button.connect("toggled", self.switch_file, file)
		
			return button
	
	# Activate another tab
	def switch_file(self, widget: Gtk.Widget, file: _FileRecord) -> bool:
		"""Switch the currently displayed file to `path`."""
		if not widget.get_active():
			return True
		
		self.current_file = file
		self.gtk_builder.get_object("ContentList").set_model(file.store)
		
		mixtype = ("TD", "RA", "TS")[file.container.get_mixtype()]
		self.set_statusbar(" ".join((mixtype, "MIX contains", str(file.container.get_filecount()), "files.")))
		
		return True
	
	def set_statusbar(self, text: str) -> None:
		self.gtk_builder.get_object("StatusBar").set_text(text)
	
	# Method that creates a main window in the first instance.
	# Can be run multiple times on behalf of remote controllers.
	def do_activate(self) -> None:
		"""Create a new main window or present an existing one."""
		# FIXME: Edit multiple files in tabs
		if self.window is None:
			self.window = self.gtk_builder.get_object("MainWindow")
			self.add_window(self.window)
			self.set_statusbar("This is alpha software. Use at your own risk!")
			self.window.show()
		else:
			self.window.present()
			print("Activated main window on behalf of remote controller.", file=sys.stderr)
	
	# Method run when the application is told
	# to open files from outside.
	def do_open(self, files: list, *args) -> None:
		"""Open `files` and create a new tab for each of them."""
		self.do_activate()
		self.mark_busy()
		
		# Open the files
		for file in files:
			button = self.open_file(file.get_path())
		
		# Switch to last opened file
		if isinstance(button, Gtk.RadioButton):
			button.toggled() if button.get_active() else button.set_active(True)
		
			# Switch to Close button and enable ContentList
			self.gtk_builder.get_object("Toolbar.Quit").hide()
			self.gtk_builder.get_object("Toolbar.Close").show()
			self.gtk_builder.get_object("ContentList").set_sensitive(True)
		
		self.unmark_busy()
	
	def save_settings(self) -> None:
		"""Save configuration to file"""
		try:
			config_stream = open(self.config_file, "w", encoding="ascii")
		except OSError:
			messagebox("Error writing configuration file.", "e")
		else:
			self.settings.write(config_stream, True)
			config_stream.close()
			print("Saved configuration file.", file=sys.stderr)


# <old_code>
		
class OldWindowController(object):
	"""Legacy window controller"""
	def __init__(self, application):
	
		self.Application = application

		GtkBuilder = application.gtk_builder

		self.GtkBuilder          = GtkBuilder
		self.MainWindow          = GtkBuilder.get_object("MainWindow")
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
		self.Application.set_statusbar(str(text))

	def set_titlebar(self, text):
		pass

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
	# HINT: GLib.unix_signal_add()
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	
	# FIXME: Remove in final version
	print("Mixtool is running on Python {0[0]}.{0[1]} using PyGObject {1[0]}.{1[1]} and GTK+ {2[0]}.{2[1]}."
		.format(sys.version_info, gi.version_info, (Gtk.get_major_version(), Gtk.get_minor_version())), file=sys.stderr)
	
	# Initialize GLib's treads capability
	GLib.threads_init()
	
	# Initialize Application
	GLib.set_prgname("mixtool")
	GLib.set_application_name("Mixtool")
	application = Mixtool()
	
	# Start GUI
	# FIXME: All exceptions raised from inside are caught by GTK!
	#        I need to look for a deeper place to catch them all.
	status = application.run(sys.argv)
	print("GTK+ returned.", file=sys.stderr)
	
	return status

# A simple, instance-independent messagebox
def messagebox(text: str, type_: str = "i", parent: Gtk.Window = None, *, secondary: str = None) -> None:
	"""Display a dialog box containing `text` and an OK button.
	
	`type_` can be 'i' for information, 'e' for error or 'w' for warning.
	
	If `parent` is given, the dialog will be a child of that window and
	centered upon it.
	
	`secondary` can be used to display additional text. The primary text will
	appear bolder in that case.
	"""
	if type_ == "i":
		title = "Notice"
		message_type = Gtk.MessageType.INFO
	elif type_ == "e":
		title = "Error"
		message_type = Gtk.MessageType.ERROR
	elif type_ == "w":
		title = "Warning"
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
	dialog.set_title(title)
	dialog.set_position(position)
	
	if secondary is not None:
		dialog.format_secondary_text(str(secondary))
	
	dialog.run()
	dialog.destroy()


# Run the application
sys.exit(main())
