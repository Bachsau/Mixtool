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
import random
import collections
import collections.abc
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

# The data type used to keep track of open files
_FileRecord = collections.namedtuple("_FileRecord", ("path", "container", "store", "button"))

# A simple abstraction for Python's ConfigParser.
# It features implicit type conversion and defaults through prior
# registration of settings. It can used to save and read settings
# without bothering about the specifics of ConfigParser or the INI files
# themselves. It could also serve as a starting point to abstract
# platform-specific saving methods through its general API.
class Configuration(collections.abc.MutableMapping):
	"""INI file based configuration manager"""
	
	__slots__ = ("_defaults", "_parser")
	
	key_chars = frozenset("0123456789_abcdefghijklmnopqrstuvwxyz")
	
	def __init__(self) -> None:
		"""Initialize the configuration manager."""
		self._defaults = {}
		self._parser = configparser.RawConfigParser(
			None, dict, False,
			delimiters=("=",),
			comment_prefixes=(";",),
			inline_comment_prefixes=None,
			strict=True,
			empty_lines_in_values=False,
			default_section=None,
			interpolation=None
		)
		self._parser.add_section("Settings")
	
	def __getitem__(self, identifier: str):
		"""Return value of `identifier` or the registered default on errors.
		
		`KeyError` is raised if there is no such identifier.
		"""
		section = "Settings"
		default = self._defaults[identifier]
		dtype = type(default)
		
		if self._parser.has_option(section, identifier):
			try:
				if dtype is bool:
					return self._parser.getboolean(section, identifier)
				
				if dtype is int:
					return self._parser.getint(section, identifier)
				
				if dtype is float:
					return self._parser.getfloat(section, identifier)
				
				if dtype is str:
					return parse.unquote(self._parser.get(section, identifier), errors="strict")
				
				if dtype is bytes:
					return parse.unquote_to_bytes(self._parser.get(section, identifier))
			
			except ValueError:
				self._parser.remove_option(section, identifier)
				return default
		else:
			return default
	
	def __setitem__(self, identifier: str, value) -> None:
		"""Set `identifier` to `value`.
		
		`KeyError` is raised if `identifier` was not registered.
		`TypeError` is raised if `value` does not match the registered type.
		"""
		section = "Settings"
		dtype = type(self._defaults[identifier])
		
		if dtype is bool and type(value) is bool:
			self._parser.set(section, identifier, "yes" if value else "no")
		
		elif dtype is int and type(value) is int\
		  or dtype is float and type(value) is float:
			self._parser.set(section, identifier, str(value))
		
		elif dtype is str and type(value) is str:
			self._parser.set(section, identifier, parse.quote(value))
		
		elif dtype is bytes and type(value) is bytes:
			self._parser.set(section, identifier, parse.quote_from_bytes(value))
		
		else:
			raise TypeError("Not matching registered type.")
	
	def __delitem__(self, identifier: str) -> None:
		"""Remove customized value of `identifier`.
		
		Nothing is done if the value was not customized,
		but `KeyError` is raised if `identifier` was not registered."""
		if identifier in self._defaults:
			self._parser.remove_option("Settings", identifier)
		else:
			raise KeyError(identifier)
	
	def __iter__(self):
		"""Return an iterator over all registered identifiers."""
		return iter(self._defaults)
	
	def __len__(self) -> int:
		"""Return the number of registered identifiers."""
		return len(self._defaults)
	
	def register(self, identifier: str, default) -> None:
		"""Register a setting and its default value.
		
		Identifiers must consist of only lowercase letters,
		digits and underscores.
		
		The type of `default` also specifies the type returned later
		and what can be assigned.
		
		Supported types are `bool`, `int`, `float`, `str` and `bytes`.
		"""
		if type(identifier) is not str:
			raise TypeError("Identifiers must be strings.")
		
		if not self.key_chars.issuperset(identifier):
			raise ValueError("Identifier contains invalid characters.")
			
		if identifier in self._defaults:
			raise ValueError("Identifier already registered.")
		
		if type(default) not in (bool, int, float, str, bytes):
			raise TypeError("Unsupported type.")
		
		self._defaults[identifier] = default
	
	def get_default(self, identifier: str):
		"""Return the default value of `identifier`.
		
		`KeyError` is raised if there is no such identifier.
		"""
		return self._defaults[identifier]
	
	def read_file(self, file: str) -> None:
		"""Read and parse a configuration file."""
		with open(file, encoding="ascii") as config_stream:
			self._parser.read_file(config_stream)
	
	def write_file(self, file: str) -> None:
		"""Save the configuration."""
		with open(file, "w", encoding="ascii") as config_stream:
			self._parser.write(config_stream, True)


# Main application controller
class Mixtool(Gtk.Application):
	"""Application management class"""
	
	# The GtkFileFilter used by open/save dialogs
	file_filter = Gtk.FileFilter()
	file_filter.set_name("MIX files")
	file_filter.add_pattern("*.mix" if sys.platform.startswith(("win", "darwin")) else "*.[Mm][Ii][Xx]")
	
	# Object initializer
	def __init__(self, application_id: str, flags: Gio.ApplicationFlags) -> None:
		"""Initialize the Mixtool instance"""
		Gtk.Application.__init__(self, application_id=application_id, flags=flags)
		
		# Initialize instance attributes
		self._settings_failed = False
		self._builder = None
		self._files = []
		self._current_file = None
		self.home_dir = None
		self.data_dir = None
		self.config_file = None
		self.settings = None
		self.motd = None
	
	# This is run when Gtk.Application initializes the first instance.
	# It is not run on any remote controllers.
	def do_startup(self) -> None:
		"""Initialize the main instance"""
		Gtk.Application.do_startup(self)
		
		self.motd = random.choice((
			"CABAL is order",
			"Don’t throw stones in glass houses without proper protection",
			"For Kane",
			"If I am cut, do I not bleed?",
			"Kane lives in death",
			"The technology of peace",
			"Tiberium is the way and the life",
			"You can’t kill the Messiah"
		))
		
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
			self.data_dir = self.home_dir + "/Library/Application Support/com.bachsau.mixtool"
		
		else:
			# Linux and others
			os_appdata = os.environ.get("XDG_DATA_HOME")
			if os_appdata is None:
				self.data_dir = self.home_dir + "/.local/share/mixtool"
			else:
				self.data_dir = os.path.realpath(os_appdata) + "/mixtool"
			del os_appdata
		
		# Create non-existent directories
		try:
			if not os.path.isdir(self.data_dir):
				os.makedirs(self.data_dir)
		except Exception as problem:
			self._settings_failed = True
			messagebox("Mixtool is unable to create its data directory.", "w", secondary="{0}:\n\"{1}\"\n\n".
				format(problem.strerror if isinstance(problem, OSError) else "Undefinable problem", self.data_dir) + "Your settings will not be retained.")
		
		# Set location of configuration file
		self.config_file = os.sep.join((self.data_dir, "settings.ini"))
		
		# Initialize configuration manager
		self.settings = Configuration()
		try:
			self.settings.read_file(self.config_file)
		except FileNotFoundError:
			pass
		except Exception as problem:
			if not self._settings_failed:
				if isinstance(problem, OSError):
					problem_description = problem.strerror
				elif isinstance(problem, UnicodeError):
					problem_description = "Contains non-ASCII characters"
				elif isinstance(problem, configparser.Error):
					problem_description = "Contains incomprehensible structures"
				else:
					problem_description = "Undefinable problem"
				
				messagebox("Mixtool is unable to read its configuration file.", "w", secondary="{0}:\n\"{1}\"\n\n".
					format(problem_description, self.config_file) + "Your settings will be reset.")
		
		# Register default settings
		self.settings.register("simplenames", True)
		self.settings.register("insertlower", True)
		self.settings.register("decrypt", True)
		self.settings.register("backup", False)
		self.settings.register("lastdir", self.home_dir)
		self.settings.register("alpha_warning", True)
		self.settings.register("deletion_warning", True)
		
		# Parse GUI file
		app_dir = os.path.dirname(os.path.realpath(__file__))
		gui_file = os.sep.join((app_dir, "res", "main.glade"))
		self._builder = Gtk.Builder.new_from_file(gui_file)
		
		# Adjustments
		self._builder.get_object("AboutDialog").set_default_response(Gtk.ResponseType.DELETE_EVENT)
		
		dummy_callback = lambda widget: True
		callback_map = {
			"on_new_clicked": dummy_callback,
			"on_open_clicked": self.invoke_open_dialog,
			"on_properties_clicked": self.invoke_properties_dialog,
			"on_optimize_clicked": dummy_callback,
			"on_insert_clicked": dummy_callback,
			"on_delete_clicked": dummy_callback,
			"on_extract_clicked": dummy_callback,
			"on_settings_clicked": self.invoke_settings_dialog,
			"on_about_clicked": self.invoke_about_dialog,
			"on_close_clicked": self.close_current_file,
			"on_quit_clicked": self.close_window,
			"on_donate_clicked": self.open_donation_website,
			"update_properties_dialog": self.update_properties_dialog,
			"restore_default_settings": dummy_callback
		}
		self._builder.connect_signals(callback_map)
	
	def invoke_properties_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a dialog to modify the current file’s properties."""
		if self._current_file is None:
			# TODO: Replace by disabling the button
			messagebox("Properties can only be set for an open file.", "e", widget.get_toplevel())
		else:
			dialog = self._builder.get_object("PropertiesDialog")
			mixtype_dropdown = self._builder.get_object("Properties.Type")
			current_mixtype = self._current_file.container.get_type()
			
			mixtype_dropdown.set_active_id(str(current_mixtype))
			self._builder.get_object("PropertiesDialog.OK").grab_focus()
			response = dialog.run()
			dialog.hide()
			
			if response == Gtk.ResponseType.OK:
				selected_mixtype = int(mixtype_dropdown.get_active_id())
				encrypt_checkbox = self._builder.get_object("Properties.Encrypted")
				checksum_checkbox = self._builder.get_object("Properties.Checksum")
				
				if selected_mixtype != current_mixtype:
					messagebox("Conversion is not implemented yet.", "e", widget.get_toplevel())
				
				self._current_file.container.is_encrypted = encrypt_checkbox.get_active()
				self._current_file.container.has_checksum = checksum_checkbox.get_active()
		
		return True
	
	def update_properties_dialog(self, widget: Gtk.Widget) -> bool:
		"""Update the properties dialog to reflect the choosen MIX type."""
		mixtype = int(widget.get_active_id())
		encrypt_checkbox = self._builder.get_object("Properties.Encrypted")
		checksum_checkbox = self._builder.get_object("Properties.Checksum")
		
		if mixtype < 1 or self.settings["decrypt"]:
			encrypt_checkbox.set_sensitive(False)
			encrypt_checkbox.set_active(False)
		else:
			encrypt_checkbox.set_sensitive(True)
			encrypt_checkbox.set_active(self._current_file.container.is_encrypted)
		
		if mixtype < 1:
			checksum_checkbox.set_sensitive(False)
			checksum_checkbox.set_active(False)
		else:
			checksum_checkbox.set_sensitive(True)
			checksum_checkbox.set_active(self._current_file.container.has_checksum)
		
		return True
	
	def invoke_settings_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a dialog with current settings and save any changes."""
		dialog = self._builder.get_object("SettingsDialog")
		checkboxes = (
			(self._builder.get_object("Settings.SimpleNames"), "simplenames"),
			(self._builder.get_object("Settings.InsertLower"), "insertlower"),
			(self._builder.get_object("Settings.Decrypt"), "decrypt"),
			(self._builder.get_object("Settings.Backup"), "backup")
		)
		
		# Push current settings to dialog
		for checkbox, setting in checkboxes:
			checkbox.set_active(self.settings[setting])
		
		# Show the dialog
		self._builder.get_object("SettingsDialog.OK").grab_focus()
		response = dialog.run()
		dialog.hide()
		
		if response == Gtk.ResponseType.OK:
			# Save new settings
			for checkbox, setting in checkboxes:
				self.settings[setting] = checkbox.get_active()
			if self._builder.get_object("Settings.ResetWarnings").get_active():
				del self.settings["alpha_warning"], self.settings["deletion_warning"]
			self.save_settings()
			
			# Apply decrypt setting
			if self.settings["decrypt"]:
				for file in self._files:
					file.container.is_encrypted = False
		
		return True
	
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
			self._builder.get_object("MainWindow").destroy()
		finally:
			Gtk.Application.do_shutdown(self)
	
	# Show about dialog
	def invoke_about_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a dialog with information on Mixtool."""
		dialog = self._builder.get_object("AboutDialog")
		dialog.get_widget_for_response(Gtk.ResponseType.DELETE_EVENT).grab_focus()
		dialog.run()
		dialog.hide()
		return True
	
	# Open donation website in default browser
	def open_donation_website(self, widget: Gtk.Widget) -> bool:
		"""Open donation website in default browser."""
		Gtk.show_uri_on_window(widget.get_toplevel(), "http://go.bachsau.com/mtdonate", Gtk.get_current_event_time())
		return True
		
	# Callback to create a new file by using a dialog
	def invoke_new_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a file chooser dialog and create a new file."""
		messagebox("Not implemented", "w", self.MainWindow, secondary="Call to `invoke_new_dialog()` method.")
		return True
	
	# Callback to open files by using a dialog
	def invoke_open_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a file chooser dialog and open selected files."""
		window = widget.get_toplevel()
		lastdir = self.settings["lastdir"]
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
				self.settings["lastdir"] = newdir
				self.save_settings()
			
			# Open the files
			self.open_files(dialog.get_files())
		
		dialog.destroy()
		return True
	
	def open_files(self, files: list) -> None:
		"""Try to open all files in `files`."""
		window = self.get_active_window()
		errors = []
		
		self.mark_busy()
		
		for file in files:
			path = os.path.realpath(file.get_path())
			
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
					store = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_ULONG, GObject.TYPE_ULONG, GObject.TYPE_ULONG)
					store.set_sort_column_id(0, Gtk.SortType.ASCENDING)
					for record in container.get_contents():
						store.append((
							record.name,
							record.size,
							record.offset,
							record.alloc - record.size  # = Overhead
						))
					
					# Add a button
					button = Gtk.RadioButton.new_with_label_from_widget(already_open.button if self._files else None, os.path.basename(path))
					button.set_mode(False)
					button.get_child().set_ellipsize(Pango.EllipsizeMode.END)
					button.set_tooltip_text(path)
					self._builder.get_object("TabBar").pack_start(button, True, True, 0)
					button.show()
					
					# Create the file record
					file = _FileRecord(path, container, store, button)
					self._files.append(file)
					
					# Connect the signal
					button.connect("toggled", self.switch_file, file)
		
		if len(files) - len(errors) > 0:
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
	
	# Switch to another tab
	def switch_file(self, widget: Gtk.Widget, file: _FileRecord) -> bool:
		"""Switch the currently displayed file to `path`."""
		if widget.get_active():
			mixtype = ("TD", "RA", "TS")[file.container.get_type()]
			status = " ".join((mixtype, "MIX contains", str(file.container.get_filecount()), "files."))
			title = widget.get_label() + " – Mixtool (Alpha)"
			
			self._current_file = file
			self._builder.get_object("ContentList").set_model(file.store)
			self._builder.get_object("StatusBar").set_text(status)
			self._builder.get_object("MainWindow").set_title(title)
		
		return True
	
	def update_gui(self) -> None:
		"""Enable or disable GUI elements base on current state."""
		if self._files:
			# Switch to last open file
			button = self._files[-1].button
			button.toggled() if button.get_active() else button.set_active(True)
			
			# Switch to Close button and enable ContentList
			self._builder.get_object("Toolbar.Quit").hide()
			self._builder.get_object("Toolbar.Close").show()
			self._builder.get_object("ContentList").set_sensitive(True)
		else:
			# Switch to Quit button and disable ContentList
			self._builder.get_object("Toolbar.Close").hide()
			self._builder.get_object("Toolbar.Quit").show()
			self._builder.get_object("ContentList").set_sensitive(False)
			self._builder.get_object("ContentList").set_model(self._builder.get_object("ContentStore"))
			self._builder.get_object("StatusBar").set_text(self.motd)
			self._builder.get_object("MainWindow").set_title("Mixtool")
		
		# Display tab bar only when two ore more files are open
		if len(self._files) < 2:
			self._builder.get_object("TabBar").hide()
		else:
			self._builder.get_object("TabBar").show()
	
	def update_available_actions(self) -> None:
		"""Depends on number of files in container."""
	
	# Method that creates a main window in the first instance.
	# Can be run multiple times on behalf of remote controllers.
	def do_activate(self) -> None:
		"""Create a new main window or present an existing one."""
		window = self.get_active_window()
		if window is None:
			window = self._builder.get_object("MainWindow")
			self._builder.get_object("StatusBar").set_text(self.motd)
			self.add_window(window)
			window.show()
			
			if self.settings["alpha_warning"]:
				dialog = self._builder.get_object("AlphaWarning")
				dialog.run()
				dialog.hide()
				if self._builder.get_object("AlphaWarning.Disable").get_active():
					self.settings["alpha_warning"] = False
					self.save_settings()
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
		self.activate()
		self.open_files(files)
	
	def save_settings(self) -> None:
		"""Save configuration to file."""
		if not self._settings_failed:
			try:
				self.settings.write_file(self.config_file)
			except Exception as problem:
				self._settings_failed = True
				messagebox("Mixtool is unable to save its configuration file.", "w", self.get_active_window(), secondary="{0}:\n\"{1}\"\n\n".
					format(problem.strerror if isinstance(problem, OSError) else "Undefinable problem", self.config_file) + "Your settings will not be retained.")
			else:
				print("Saved configuration file.", file=sys.stderr)


# <!-- BEGIN Old code -->
		
class OldWindowController(object):
	"""Legacy window controller"""
	def __init__(self, application):
		self.Application = application
		GtkBuilder = application._builder
		
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
				filename = rows[0][0]
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
						filename = row[0]
						self.MixFile.extract(filename, os.path.join(outpath, filename))
				else:
					self.MixFile.extract(filename, outpath)

	def get_selected_rows(self):
		rows = []
		for path in self.ContentSelector.get_selected_rows()[1]:
			rows.append(self.ContentStore[path])
		return rows



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
					self.ContentStore[treeiter][0] = inode.name

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
	
	# Initialize Application
	GLib.set_prgname("mixtool")
	GLib.set_application_name("Mixtool")
	application = Mixtool("com.bachsau.mixtool", Gio.ApplicationFlags.HANDLES_OPEN)
	
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
		position = Gtk.WindowPosition.CENTER
		skip_hint = False
	else:
		position = Gtk.WindowPosition.CENTER_ON_PARENT
		skip_hint = True
	
	dialog = Gtk.MessageDialog(
		message_type=message_type,
		buttons=Gtk.ButtonsType.OK,
		text=str(text),
		title=title,
		icon_name=icon,
		window_position=position,
		skip_taskbar_hint=skip_hint,
		skip_pager_hint=skip_hint,
		transient_for=parent,
		border_width=5
	)
	
	if secondary is not None:
		dialog.format_secondary_text(str(secondary))
	
	dialog.run()
	dialog.destroy()


# Run the application
sys.exit(main())
