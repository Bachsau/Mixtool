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
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, GObject, Gio, Pango, Gdk, Gtk

# Local modules
import mixlib

# Constants
COLUMN_ROWID    = -1
COLUMN_NAME     = 0
COLUMN_OFFSET   = 1
COLUMN_SIZE     = 2
COLUMN_OVERHEAD = 3


# FileRecord data type
_FileRecord = collections.namedtuple("_FileRecord", ("path", "container", "store", "button"))

# Main application controller
class Mixtool(Gtk.Application):
	"""Application management class"""
	
	# The GtkFileFilter used by open/save dialogs
	file_filter = Gtk.FileFilter()
	file_filter.set_name("MIX files")
	file_filter.add_pattern("*.mix" if sys.platform.startswith(("win", "darwin")) else "*.[Mm][Ii][Xx]")
	
	# Object initializer
	def __init__(self) -> None:
		"""Initialize the Mixtool instance"""
		Gtk.Application.__init__(self, application_id="com.bachsau.mixtool", flags=Gio.ApplicationFlags.HANDLES_OPEN)
		
		# Initialize instance attributes
		self._save_settings = True
		self._gtk_builder = None
		self._files = []
		self._current_file = None
		self.home_dir = None
		self.data_dir = None
		self.config_file = None
		self.settings = None
	
	# This is run when Gtk.Application initializes the first instance.
	# It is not run on any remote controllers.
	def do_startup(self) -> None:
		"""Initialize the main instance"""
		Gtk.Application.do_startup(self)
		
		# Determine a platform-specific data directory
		self.home_dir = os.path.realpath(os.path.expanduser("~"))
		
		if sys.platform.startswith("win"):
			# Microsoft Windows
			os_appdata = os.environ.get("APPDATA")
			if os_appdata is None:
				self.data_dir = self.home_dir + "\\AppData\\Roaming\\Bachsau\\Mixtool"
			else:
				self.data_dir = os.path.realpath(os_appdata) + "\\Bachsau\\Mixtool"
			del os_appdata
		
		elif sys.platform.startswith("darwin"):
			# Apple macOS
			self.data_dir = self.home_dir + "/Library/Application Support/Bachsau/Mixtool"
		
		else:
			# Linux and others
			os_appdata = os.environ.get("XDG_DATA_HOME")
			if os_appdata is None:
				self.data_dir = self.home_dir + "/.local/share/bachsau/mixtool"
			else:
				self.data_dir = os.path.realpath(os_appdata) + "/bachsau/mixtool"
			del os_appdata
		
		# Create non-existent directories
		try:
			if not os.path.isdir(self.data_dir):
				os.makedirs(self.data_dir)
		except Exception as problem:
			self._save_settings = False
			messagebox("Mixtool is unable to create its data directory.", "w", secondary="{0}:\n\"{1}\"\n\n".
				format(problem.strerror if isinstance(problem, OSError) else "Undefinable problem", self.data_dir) + "Your settings will not be retained.")
		
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
		if self._save_settings:
			try:
				config_stream = open(self.config_file, encoding="ascii")
			except FileNotFoundError:
				pass
			except Exception as problem:
				self._save_settings = False
				messagebox("Mixtool is unable to access its configuration file.", "w", secondary="{0}:\n\"{1}\"\n\n".
					format(problem.strerror if isinstance(problem, OSError) else "Undefinable problem", self.config_file) + "Your settings will not be retained.")
			else:
				try:
					self.settings.read_file(config_stream)
				except Exception as problem:
					if isinstance(problem, UnicodeError):
						problem_description = "Contains non-ASCII characters"
					elif isinstance(problem, configparser.Error):
						problem_description = "Contains incomprehensible structures"
					else:
						problem_description = "Undefinable problem"
					
					messagebox("Mixtool is unable to parse its configuration file.", "w", secondary="{0}:\n\"{1}\"\n\n".
						format(problem_description, self.config_file) + "Your settings will be reset.")
				
				config_stream.close()
		
		# Parse GUI file
		gui_file = os.sep.join((os.path.dirname(os.path.realpath(__file__)), "gui.glade"))
		self._gtk_builder = Gtk.Builder.new_from_file(gui_file)
		
		dummy_callback = lambda widget: True
		callback_map = {
			"close_window": self.close_window,
			"invoke_new_dialog": self.invoke_new_dialog,
			"invoke_open_dialog": self.invoke_open_dialog,
			"optimize_mixfile": dummy_callback,
			"invoke_insert_dialog": dummy_callback,
			"delete_selected": dummy_callback,
			"invoke_extract_dialog": dummy_callback,
			"invoke_search_dialog": dummy_callback,
			"invoke_properties_dialog": self.invoke_properties_dialog,
			"invoke_settings_dialog": self.invoke_settings_dialog,
			"invoke_about_dialog": self.invoke_about_dialog,
			"invoke_extract_dialog": dummy_callback,
			"show_donate_uri": self.show_donate_uri,
			"close_current_file": self.close_current_file
		}
		self._gtk_builder.connect_signals(callback_map)
	
	def invoke_properties_dialog(self, widget: Gtk.Widget) -> bool:
		dialog = self._gtk_builder.get_object("PropertiesDialog")
		dialog.run()
		dialog.hide()
	
	def invoke_settings_dialog(self, widget: Gtk.Widget) -> bool:
		dialog = self._gtk_builder.get_object("SettingsDialog")
		checkboxes = [
			(self._gtk_builder.get_object("Settings.SimpleNames"), "simplenames"),
			(self._gtk_builder.get_object("Settings.InsertLower"), "insertlower"),
			(self._gtk_builder.get_object("Settings.Decrypt"), "decrypt"),
			(self._gtk_builder.get_object("Settings.Backup"), "backup"),
		]
		
		# Push current settings to dialog
		for checkbox, setting in checkboxes:
			try:
				checkbox.set_active(self.settings.getboolean("Mixtool", setting))
			except:
				pass
		
		# Show the dialog
		response = dialog.run()
		dialog.hide()
		
		if response == Gtk.ResponseType.OK:
			# Save new settings
			for checkbox, setting in checkboxes:
				self.settings["Mixtool"][setting] = "yes" if checkbox.get_active() else "no"
			self.save_settings()
	
	# Close file in current tab
	def close_current_file(self, widget: Gtk.Widget) -> bool:
		"""Close the currently active file."""
		file = self._current_file
		
		# Close the file
		file.container.finalize().close()
		
		# Remove all references
		self._current_file = None
		self._files.remove(file)
		file.button.destroy()
		
		self.update_gui()
		
		return True
		
	# This method is labeled as "Quit" in the GUI,
	# because it is the ultimate result.
	def close_window(self, widget: Gtk.Widget, event: Gdk.Event = None) -> bool:
		"""Close the application window."""
		window = widget.get_toplevel()
		self._current_file = None
		
		while(self._files):
			file = self._files.pop()
			file.container.finalize().close()
			file.button.destroy()
		
		self.update_gui()
		
		# Hide and remove the window
		window.hide()
		self.remove_window(window)
		
		return True
	
	# Run on the primary instance immediately after the main loop terminates.
	def do_shutdown(self) -> None:
		"""Finalize the application."""
		try:
			self._gtk_builder.get_object("MainWindow").destroy()
		finally:
			Gtk.Application.do_shutdown(self)
	
	# Show about dialog
	def invoke_about_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a dialog with information on Mixtool."""
		dialog = self._gtk_builder.get_object("AboutDialog")
		dialog.set_default_response(Gtk.ResponseType.DELETE_EVENT)
		dialog.run()
		dialog.hide()
		return True
	
	# Open donation website in default browser
	def show_donate_uri(self, widget: Gtk.Widget) -> bool:
		"""Open donation website in default browser."""
		Gtk.show_uri_on_window(widget.get_toplevel(), "http://go.bachsau.com/mtdonate", Gtk.get_current_event_time())
		return True
		
	# Callback to create a new file by using a dialog
	def invoke_new_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a file chooser dialog and create a new file."""
		messagebox("Not implemented", "w", self.MainWindow, secondary="Call to `invoke_new_dialog()` method.")
	
	# Callback to open files by using a dialog
	def invoke_open_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a file chooser dialog and open selected files."""
		window = widget.get_toplevel()
		lastdir = parse.unquote(self.settings["Mixtool"]["lastdir"])
		dialog = Gtk.FileChooserNative.new("Open MIX file", window, Gtk.FileChooserAction.OPEN, "_Open", "_Cancel")
		dialog.set_select_multiple(True)
		dialog.add_filter(self.file_filter)
		dialog.set_filter(self.file_filter)
		dialog.set_current_folder(lastdir)
		response = dialog.run()
		dialog.hide()
		
		if response == Gtk.ResponseType.ACCEPT:
			# Save last used directory
			newdir = dialog.get_current_folder()
			if newdir != lastdir:
				self.settings["Mixtool"]["lastdir"] = parse.quote(newdir)
				self.save_settings()
			
			# Open the files
			self.open_files(window, dialog.get_filenames())
		
		dialog.destroy()
		return True
	
	def open_files(self, window: Gtk.Window, paths: list) -> None:
		"""Try to open the files in `paths`.
		
		`window` is used as the parent for error messages.
		"""
		errors = []
		
		self.mark_busy()
		
		for path in paths:
			path = os.path.realpath(path)
			
			# Check if file is already open
			for already_open in self._files:
				if os.path.samefile(already_open.path, path):
					errors.append((1, path))
					break
			else:
				try:
					# TODO: Catch errors from mixlib.MixFile separately,
					# so stream can be closed cleanly
					stream = open(path, "r+b")
					container = mixlib.MixFile(stream)
				except Exception:
					errors.append((2, path))
				else:
					# Initialize a Gtk.ListStore
					store = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_UINT, GObject.TYPE_UINT, GObject.TYPE_UINT)
					store.set_sort_column_id(0, Gtk.SortType.ASCENDING)
					for record in container.get_contents():
						store.append((
							record[0], # Name
							record[2], # Offset
							record[1], # Size
							record[3] - record[1] # Alloc - Size = Overhead
						))
					
					# Add a button
					button = Gtk.RadioButton.new_with_label_from_widget(already_open.button if self._files else None, os.path.basename(path))
					button.set_mode(False)
					button.get_child().set_ellipsize(Pango.EllipsizeMode.END)
					button.set_tooltip_text(path)
					self._gtk_builder.get_object("TabBar").pack_start(button, True, True, 0)
					button.show()
					
					# Create the file record
					file = _FileRecord(path, container, store, button)
					self._files.append(file)
					
					# Connect the signal
					button.connect("toggled", self.switch_file, file)
		
		if len(paths) - len(errors) > 0:
			self.update_gui()
		
		self.unmark_busy()
		
		# Now handle the errors
		if errors:
			for errno, path in errors:
				# TODO: Show only one dialog per error or only one dialog at all.
				if errno == 1:
					messagebox("This file is already open and can only be opened once:", "e", window, secondary=path)
				elif errno == 2:
					messagebox("Error loading MIX file:" ,"e", window, secondary=path)
				else:
					messagebox("An unknown error occured while trying to open:" ,"e", window, secondary=path)
	
	# Activate another tab
	def switch_file(self, widget: Gtk.Widget, file: _FileRecord) -> bool:
		"""Switch the currently displayed file to `path`."""
		if widget.get_active():
			mixtype = ("TD", "RA", "TS")[file.container.get_mixtype()]
			status = " ".join((mixtype, "MIX contains", str(file.container.get_filecount()), "files."))
			title = widget.get_label() + " – Mixtool (Alpha)"
			
			self._current_file = file
			self._gtk_builder.get_object("ContentList").set_model(file.store)
			self._gtk_builder.get_object("StatusBar").set_text(status)
			self._gtk_builder.get_object("MainWindow").set_title(title)
		
		return True
	
	def update_gui(self) -> None:
		"""Enable or disable GUI elements base on current state."""
		if self._files:
			# Switch to last open file
			button = self._files[-1].button
			button.toggled() if button.get_active() else button.set_active(True)
			
			# Switch to Close button and enable ContentList
			self._gtk_builder.get_object("Toolbar.Quit").hide()
			self._gtk_builder.get_object("Toolbar.Close").show()
			self._gtk_builder.get_object("ContentList").set_sensitive(True)
		else:
			# Switch to Quit button and disable ContentList
			self._gtk_builder.get_object("Toolbar.Close").hide()
			self._gtk_builder.get_object("Toolbar.Quit").show()
			self._gtk_builder.get_object("ContentList").set_sensitive(False)
			self._gtk_builder.get_object("ContentList").set_model(self._gtk_builder.get_object("DummyStore"))
			self._gtk_builder.get_object("StatusBar").set_text("")
			self._gtk_builder.get_object("MainWindow").set_title("Mixtool (Alpha)")
		
		# Display tab bar only when two ore more files are open
		if len(self._files) < 2:
			self._gtk_builder.get_object("TabBar").hide()
		else:
			self._gtk_builder.get_object("TabBar").show()
	
	# Method that creates a main window in the first instance.
	# Can be run multiple times on behalf of remote controllers.
	def do_activate(self) -> None:
		"""Create a new main window or present an existing one."""
		window = self.get_active_window()
		if window is None:
			window = self._gtk_builder.get_object("MainWindow")
			self.add_window(window)
			window.show()
		else:
			window.present()
			print("Activated main window on behalf of remote controller.", file=sys.stderr)
	
	# Method run when the application is told
	# to open files from outside.
	#
	# The signature should be "do_open(self, files: list, hint: str)",
	# but we get the number of files and some tuple instead.
	def do_open(self, files: list, *args) -> None:
		"""Open `files` and create a new tab for each of them."""
		self.do_activate()
		window = self.get_active_window()
		
		# Get paths from the `Gio.GFile` objects
		paths = [file.get_path() for file in files]
		
		# Open the files
		self.open_files(window, paths)
	
	def save_settings(self) -> None:
		"""Save configuration to file."""
		if self._save_settings:
			try:
				config_stream = open(self.config_file, "w", encoding="ascii")
			except Exception as problem:
				self._save_settings = False
				messagebox("Mixtool is unable to save its configuration file.", "w", self.get_active_window(), secondary="{0}:\n\"{1}\"\n\n".
					format(problem.strerror if isinstance(problem, OSError) else "Undefinable problem", self.config_file) + "Your settings will not be retained.")
			else:
				self.settings.write(config_stream, True)
				config_stream.close()
				print("Saved configuration file.", file=sys.stderr)


# <!-- BEGIN Old code -->
		
class OldWindowController(object):
	"""Legacy window controller"""
	def __init__(self, application):
		self.Application = application
		GtkBuilder = application._gtk_builder
		
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
	
			
	def optimize(self, *args):
		self.MixFile.write_index(True)
		self.refresh()

			
	def refresh(self):
		messagebox("Not implemented", "w", self.MainWindow, secondary="Call to legacy `refresh()` method.")
		

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
				
# <!-- END Old code -->


# Starter
def main() -> int:
	"""Run the Mixtool application and return a status code."""
	# Since GTK+ does not support KeyboardInterrupt, reset SIGINT to default.
	# TODO: Find and implement a better way to handle this.
	# HINT: GLib.unix_signal_add()
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	
	# FIXME: Remove in final version
	print("Mixtool is running on Python {0[0]}.{0[1]} using PyGObject {1[0]}.{1[1]} and GTK+ {2[0]}.{2[1]}.".
		format(sys.version_info, gi.version_info, (Gtk.get_major_version(), Gtk.get_minor_version())), file=sys.stderr)
	
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
		message_type = Gtk.MessageType.INFO
		title = "Notice"
		icon = "gtk-dialog-info"
	elif type_ == "e":
		message_type = Gtk.MessageType.ERROR
		title = "Error"
		icon = "gtk-dialog-error"
	elif type_ == "w":
		message_type = Gtk.MessageType.WARNING
		title = "Warning"
		icon = "gtk-dialog-warning"
	else:
		raise ValueError("Invalid message type.")
	
	if parent is None:
		flags = Gtk.DialogFlags(0)
		position = Gtk.WindowPosition.CENTER
		skip_taskbar = False
	else:
		flags = Gtk.DialogFlags.DESTROY_WITH_PARENT
		position = Gtk.WindowPosition.CENTER_ON_PARENT
		skip_taskbar = True
	
	dialog = Gtk.MessageDialog(parent, flags, message_type, Gtk.ButtonsType.OK, str(text))
	dialog.set_title(title)
	dialog.set_icon_name(icon)
	dialog.set_position(position)
	dialog.set_skip_taskbar_hint(skip_taskbar)
	dialog.set_skip_pager_hint(skip_taskbar)
	
	if secondary is not None:
		dialog.format_secondary_text(str(secondary))
	
	dialog.run()
	dialog.destroy()


# Run the application
sys.exit(main())
