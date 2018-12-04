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
__author__ = "Bachsau"

# Standard modules
import sys
import os
import signal
import random
import uuid
import collections
import collections.abc
import configparser
from urllib import parse
import traceback  # for debugging

# Third party modules
import gi
gi.require_version("Pango", "1.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, GObject, Gio, Pango, Gdk, Gtk

# Local modules
import mixlib


# The data type used to keep track of open files
FileRecord = collections.namedtuple("FileRecord", ("path", "stat", "container", "store", "button", "isnew"))


# A simple abstraction for Python's ConfigParser.
# It features implicit type conversion and defaults through prior
# registration of settings. It can be used to save and read settings
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
		
		if self._parser.has_option(section, identifier):
			dtype = type(default)
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
		return iter(self._defaults.keys())
	
	def __len__(self) -> int:
		"""Return the number of registered settings."""
		return len(self._defaults)
	
	def __contains__(self, identifier) -> bool:
		"""Return True if `identifier` is registered, else False."""
		return identifier in self._defaults
	
	def keys(self):
		"""Return a set-like object providing a view on registered identifiers."""
		return self._defaults.keys()
	
	def clear(self) -> None:
		"""Remove all customized values, reverting to the registered defaults."""
		section = "Settings"
		for identifier in self._defaults.keys():
			self._parser.remove_option(section, identifier)
	
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
	
	def load(self, file: str) -> None:
		"""Read and parse a configuration file."""
		with open(file, encoding="ascii") as config_stream:
			self._parser.read_file(config_stream)
	
	def save(self, file: str) -> None:
		"""Save the configuration."""
		with open(file, "w", encoding="ascii") as config_stream:
			self._parser.write(config_stream, False)


# Main application controller
class Mixtool(Gtk.Application):
	"""Application management class"""
	
	# The GtkFileFilter used by open/save dialogs
	file_filter = Gtk.FileFilter()
	file_filter.set_name("MIX files")
	file_filter.add_pattern("*.[Mm][Ii][Xx]")
	
	# Object initializer
	def __init__(self, application_id: str, flags: Gio.ApplicationFlags) -> None:
		"""Initialize the Mixtool instance."""
		Gtk.Application.__init__(self, application_id=application_id, flags=flags)
		self.set_resource_base_path(None)
		
		# Initialize instance attributes
		self._data_path_blocked = False
		self._builder = None
		self._files = []
		self._current_file = None
		self.installation_id = None
		self.home_path = None
		self.data_path = None
		self.config_file = None
		self.settings = None
		self.motd = None
	
	# This is run when Gtk.Application initializes the first instance.
	# It is not run on any remote controllers.
	def do_startup(self) -> None:
		"""Set up the application."""
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
		
		# Determine the platform-specific data directory
		self.home_path = os.path.realpath(os.path.expanduser("~"))
		
		if sys.platform.startswith("win"):
			# Microsoft Windows
			os_appdata = os.environ.get("APPDATA")
			if os_appdata is None:
				self.data_path = self.home_path + "\\AppData\\Roaming\\Bachsau\\Mixtool"
			else:
				self.data_path = os.path.realpath(os_appdata) + "\\Bachsau\\Mixtool"
			del os_appdata
		elif sys.platform.startswith("darwin"):
			# Apple macOS
			self.data_path = self.home_path + "/Library/Application Support/com.bachsau.mixtool"
		else:
			# Linux and others
			os_appdata = os.environ.get("XDG_DATA_HOME")
			if os_appdata is None:
				self.data_path = self.home_path + "/.local/share/mixtool"
			else:
				self.data_path = os.path.realpath(os_appdata) + "/mixtool"
			del os_appdata
		
		# Create non-existent directories
		if not os.path.isdir(self.data_path):
			try:
				os.makedirs(self.data_path, 448)
			except Exception as problem:
				self._data_path_blocked = True
				if isinstance(problem, OSError):
					problem_description = problem.strerror
				else:
					problem_description = "Internal error"
				messagebox(
					"Mixtool was not able to create its data directory.", "w",
					secondary="{0}:\n{1}\n\n".format(problem_description, self.data_path)
					+ "Your settings will not be retained."
				)
		
		# Set path to configuration file
		self.config_file = os.sep.join((self.data_path, "settings.ini"))
		
		# Set up the configuration manager
		self.settings = Configuration()
		self.settings.register("installation_id", 0)
		self.settings.register("simplenames", True)
		self.settings.register("insertlower", True)
		self.settings.register("decrypt", True)
		self.settings.register("backup", False)
		self.settings.register("extracttolast", True)
		self.settings.register("nomotd", False)
		self.settings.register("browse_path", self.home_path)
		self.settings.register("alpha_warning", True)
		self.settings.register("deletion_warning", True)
		
		if not self._data_path_blocked:
			try:
				self.settings.load(self.config_file)
			except FileNotFoundError:
				pass
			except Exception as problem:
				if isinstance(problem, OSError):
					problem_description = problem.strerror
				elif isinstance(problem, UnicodeError):
					problem_description = "Contains non-ASCII characters"
				elif isinstance(problem, configparser.Error):
					problem_description = "Contains incomprehensible structures"
				else:
					problem_description = "Internal error"
				messagebox(
					"Mixtool is unable to read its configuration file.", "w",
					secondary="{0}:\n{1}\n\n".format(problem_description, self.data_path)
					+ "Your settings will be reset."
				)
		
		# Initialize the installation id
		# (to be used with online features)
		try:
			installation_id = uuid.UUID(int=self.settings["installation_id"])
		except ValueError:
			installation_id = None
		if installation_id is not None and installation_id.version == 4:
			self.installation_id = installation_id
		else:
			installation_id = uuid.uuid4()
			self.settings["installation_id"] = installation_id.int
			if self.save_settings():
				self.installation_id = installation_id
		
		# Parse GUI file
		app_path = os.path.dirname(os.path.realpath(__file__))
		gui_file = os.sep.join((app_path, "res", "main.glade"))
		self._builder = Gtk.Builder.new_from_file(gui_file)
		
		dummy_callback = lambda widget: True
		callback_map = {
			"on_new_clicked": self.invoke_new_dialog,
			"on_open_clicked": self.invoke_open_dialog,
			"on_properties_clicked": self.invoke_properties_dialog,
			"on_optimize_clicked": dummy_callback,
			"on_add_clicked": dummy_callback,
			"on_remove_clicked": dummy_callback,
			"on_extract_clicked": dummy_callback,
			"on_settings_clicked": self.invoke_settings_dialog,
			"on_about_clicked": self.invoke_about_dialog,
			"on_close_clicked": self.close_current_file,
			"on_quit_clicked": self.close_window,
			"on_donate_clicked": self.open_donation_website,
			"update_properties_dialog": self.update_properties_dialog,
			"restore_default_settings": self.restore_default_settings
		}
		self._builder.connect_signals(callback_map)
		
		# Prepare GUI
		if not self.settings["nomotd"]:
			self._builder.get_object("StatusBar").set_text(self.motd)
	
	def invoke_properties_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a dialog to modify the current file’s properties."""
		if self._current_file is None:
			# TODO: Replace by disabling the button
			messagebox("Properties can only be set for an open file.", "e", widget.get_toplevel())
		else:
			dialog = self._builder.get_object("PropertiesDialog")
			mixtype_dropdown = self._builder.get_object("Properties.Type")
			current_mixtype = self._current_file.container.get_version()
			
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
		
		# The updater returns a tuple of checkboxes to not repeat
		# ourselfs when it comes to saving
		checkboxes = self._update_settings_dialog(dialog, False)
		
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
			
			if not self._files:
				self._builder.get_object("StatusBar").set_text(
					"Ready" if self.settings["nomotd"] else self.motd
				)
		
		return True
	
	def restore_default_settings(self, widget: Gtk.Widget) -> bool:
		"""Set all widgets in the settings dialog to reflect the defaults."""
		dialog = self._builder.get_object("SettingsDialog")
		self._update_settings_dialog(dialog, True)
		return True
	
	def _update_settings_dialog(self, dialog, defaults: bool) -> tuple:
		"""Populate `dialog` with the current or default settings."""
		checkboxes = (
			(self._builder.get_object("Settings.SimpleNames"), "simplenames"),
			(self._builder.get_object("Settings.InsertLower"), "insertlower"),
			(self._builder.get_object("Settings.Decrypt"), "decrypt"),
			(self._builder.get_object("Settings.Backup"), "backup"),
			(self._builder.get_object("Settings.ExtractToLast"), "extracttolast"),
			(self._builder.get_object("Settings.DisableMOTD"), "nomotd")
		)
		
		# Push current settings to dialog
		self._builder.get_object("Settings.ExtractToFile").set_active(True)
		if defaults:
			for checkbox, setting in checkboxes:
				checkbox.set_active(self.settings.get_default(setting))
			self._builder.get_object("Settings.ResetWarnings").set_active(True)
		else:
			for checkbox, setting in checkboxes:
				checkbox.set_active(self.settings[setting])
			self._builder.get_object("Settings.ResetWarnings").set_active(False)
		
		# Return the tuple of checkboxes to be used for saving
		return checkboxes
	
	def _close_file(self, record: FileRecord) -> None:
		"""Close the file referenced by `record`."""
		record.container.finalize().close()
		if record.isnew:
			try:
				if not os.stat(record.path).st_size:
					os.remove(record.path)
			except OSError:
				pass
		
		self._files.remove(record)
		record.button.destroy()
	
	def close_current_file(self, widget: Gtk.Widget) -> bool:
		"""Close the currently active file."""
		self._close_file(self._current_file)
		self._update_gui()
		return True
	
	# This method is labeled as "Quit" in the GUI,
	# because it is the ultimate result.
	def close_window(self, widget: Gtk.Widget, event: Gdk.Event = None) -> bool:
		"""Close the application window."""
		window = widget.get_toplevel()
		
		while(self._files):
			self._close_file(self._files[-1])
		self._update_gui()
		
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
	
	def invoke_about_dialog(self, widget: Gtk.Widget) -> bool:
		"""Display a dialog with information on Mixtool."""
		dialog = self._builder.get_object("AboutDialog")
		dialog.get_widget_for_response(Gtk.ResponseType.DELETE_EVENT).grab_focus()
		dialog.run()
		dialog.hide()
		return True
	
	def open_donation_website(self, widget: Gtk.Widget) -> bool:
		"""Open donation website in default browser."""
		Gtk.show_uri_on_window(widget.get_toplevel(), "http://go.bachsau.com/mtdonate", Gtk.get_current_event_time())
		return True
		
	# Callback to create a new file by using a dialog
	def invoke_new_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a file chooser dialog and create a new file."""
		window = widget.get_toplevel()
		saved_path = self.settings["browse_path"]
		browse_path = saved_path if os.path.isdir(saved_path) else self.home_path
		suggestion = "new"
		suggested = suggestion + ".mix"
		i = 1
		while os.path.lexists(os.sep.join((browse_path, suggested))):
			suggested = suggestion + str(i) + ".mix"
			i += 1
		version_chooser = Gtk.ComboBoxText()
		version_chooser.append("TD", "1 – TD")
		version_chooser.append("RA", "2 – RA")
		version_chooser.append("TS", "3 – TS, RA2, YR")
		version_chooser.append("RG", "4 – RG")
		version_chooser.set_active_id("TS")
		version_label = Gtk.Label.new_with_mnemonic("_Version:")
		version_label.set_mnemonic_widget(version_chooser)
		version_box = Gtk.Box(
			orientation=Gtk.Orientation.HORIZONTAL,
			spacing=5
		)
		version_box.pack_start(version_label, False, True, 0)
		version_box.pack_start(version_chooser, False, True, 0)
		version_box.show_all()
		dialog = Gtk.FileChooserDialog(
			title="Create MIX file",
			transient_for=window,
			action=Gtk.FileChooserAction.SAVE,
			do_overwrite_confirmation=True,
			extra_widget=version_box,
			filter=self.file_filter
		)
		try:
			dialog.add_buttons(
				"_Cancel", Gtk.ResponseType.CANCEL,
				"_Save", Gtk.ResponseType.ACCEPT
			)
			dialog.set_current_folder(browse_path)
			dialog.set_current_name(suggested)
			response = dialog.run()
			dialog.hide()
			if response == Gtk.ResponseType.ACCEPT:
				# Save last used directory
				browse_path = dialog.get_current_folder()
				if browse_path != saved_path:
					self.settings["browse_path"] = browse_path
					self.save_settings()
				
				# Open the files
				version = version_chooser.get_active_id()
				self._open_files(dialog.get_files(), getattr(mixlib.Version, version))
		finally:
			dialog.destroy()
		return True
	
	# Callback to open files by using a dialog
	def invoke_open_dialog(self, widget: Gtk.Widget) -> bool:
		"""Show a file chooser dialog and open selected files."""
		window = widget.get_toplevel()
		saved_path = self.settings["browse_path"]
		browse_path = saved_path if os.path.isdir(saved_path) else self.home_path
		dialog = Gtk.FileChooserDialog(
			title="Open MIX file",
			transient_for=window,
			action=Gtk.FileChooserAction.OPEN,
			select_multiple=True,
			filter=self.file_filter
		)
		try:
			dialog.add_buttons(
				"_Cancel", Gtk.ResponseType.CANCEL,
				"_Open", Gtk.ResponseType.ACCEPT
			)
			dialog.set_current_folder(browse_path)
			response = dialog.run()
			dialog.hide()
			if response == Gtk.ResponseType.ACCEPT:
				# Save last used directory
				browse_path = dialog.get_current_folder()
				if browse_path != saved_path:
					self.settings["browse_path"] = browse_path
					self.save_settings()
				
				# Open the files
				self._open_files(dialog.get_files())
		finally:
			dialog.destroy()
		return True
	
	def _open_files(self, files: list, new: mixlib.Version = None) -> None:
		"""Open `files` and create a new tab for each one."""
		window = self.get_active_window()
		fd_support = os.stat in os.supports_fd
		errors = []
		
		self.mark_busy()
		
		button = self._files[0].button if self._files else None
		
		for file in files:
			path = os.path.realpath(file.get_path())
			stat = None
			
			# If the file exists, stat it now
			try:
				stat = os.stat(path)
			except OSError as problem:
				if not (new is not None and isinstance(problem, FileNotFoundError)):
					errors.append((problem.errno, path))
					continue
			else:
				# File exists. Let's check if it's already open.
				continue_ = False
				for existing_record in self._files:
					if os.path.samestat(existing_record.stat, stat):
						errors.append((-1, path))
						continue_ = True
						break
				if continue_:
					continue
			
			try:
				if stat is None:
					stream = open(path, "w+b")
					isnew = True
					# Stat files that didn't exist before
					stat = os.stat(stream.fileno() if fd_support else path)
				else:
					stream = open(path, "r+b")
					isnew = False
			except OSError as problem:
				errors.append((problem.errno, path))
			else:
				container = None
				try:
					container = mixlib.MixFile(stream, new)
				except Exception:
					# FIXME: Implement finer matching as mixlib's error handling evolves
					traceback.print_exc(file=sys.stderr)
					errors.append((-2, path))
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
					button = Gtk.RadioButton.new_with_label_from_widget(button, os.path.basename(path))
					button.set_mode(False)
					button.get_child().set_ellipsize(Pango.EllipsizeMode.END)
					button.set_tooltip_text(path)
					self._builder.get_object("TabBar").pack_start(button, False, True, 0)
					button.show()
					
					# Create the file record
					record = FileRecord(path, stat, container, store, button, isnew)
					self._files.append(record)
					
					# Connect the signal
					button.connect("toggled", self.switch_file, record)
				finally:
					if container is None:
						stream.close()
		
		if len(files) - len(errors) > 0:
			self._update_gui()
		
		self.unmark_busy()
		
		# Now handle the errors
		if errors:
			if len(errors) == 1:
				err_title = "The file could not be opened."
			else:
				err_title = "Some files could not be opened."
				errors.sort(key=lambda error: error[0])
			
			err_strings = []
			err_last = None
			for errno, path in errors:
				if errno != err_last:
					err_last = errno
					err_strings.append("")
					if errno == -1:  # File is already open
						err_string = "File is already open"
					elif errno == -2:  # MIX errors
						err_string = "File is faulty"
					else:  # OS erros
						err_string = os.strerror(errno)
					err_strings.append("<b>{0}:</b>".format(err_string))
				err_strings.append("\xa0\xa0\xa0\xa0" + GLib.markup_escape_text(path))
			del err_strings[0]
			err_text = "\n".join(err_strings)
					
			messagebox(err_title, "e", window, secondary=err_text, markup=2)
	
	# Switch to another tab
	def switch_file(self, widget: Gtk.Widget, record: FileRecord) -> bool:
		"""Switch the currently displayed file to `record`."""
		if widget.get_active():
			mixtype = record.container.get_version().name
			
			status = " ".join((mixtype, "MIX contains", str(record.container.get_filecount()), "files."))
			title = widget.get_label() + " – Mixtool"
			
			self._current_file = record
			self._builder.get_object("ContentList").set_model(record.store)
			self._builder.get_object("StatusBar").set_text(status)
			self._builder.get_object("MainWindow").set_title(title)
		
		return True
	
	def _update_gui(self) -> None:
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
			# Set current file to None
			self._current_file = None
			
			# Switch to Quit button and disable ContentList
			self._builder.get_object("MainWindow").set_title("Mixtool")
			self._builder.get_object("StatusBar").set_text(
				"Ready" if self.settings["nomotd"] else self.motd
			)
			self._builder.get_object("Toolbar.Close").hide()
			self._builder.get_object("Toolbar.Quit").show()
			self._builder.get_object("ContentList").set_sensitive(False)
			self._builder.get_object("ContentList").set_model(self._builder.get_object("ContentStore"))
		
		# Display tab bar only when two ore more files are open
		if len(self._files) < 2:
			self._builder.get_object("TabBar").hide()
		else:
			self._builder.get_object("TabBar").show()
	
	def update_available_actions(self) -> None:
		"""Depends on number of files in container."""
	
	# Method run on the primary instance whenever the application
	# is invoked without parameters.
	def do_activate(self) -> None:
		"""Create a new main window or present an existing one."""
		window = self.get_active_window()
		if window is None:
			window = self._builder.get_object("MainWindow")
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
	
	# Method run on the primary instance whenever the application
	# is told to open files from outside.
	def do_open(self, files: list, *args) -> None:
		"""Open `files` in a new or existing main window."""
		self.activate()
		self._open_files(files)
	
	def save_settings(self) -> bool:
		"""Save configuration to disk."""
		if not self._data_path_blocked:
			try:
				self.settings.save(self.config_file)
			except Exception as problem:
				self._data_path_blocked = True
				if isinstance(problem, OSError):
					problem_description = problem.strerror
				else:
					problem_description = "Internal error"
				messagebox(
					"Mixtool was not able to write its configuration file.", "w",
					secondary="{0}:\n{1}\n\n".format(problem_description, self.data_path)
					+ "Changed settings will not be retained."
				)
				return False
			else:
				print("Saved configuration file.", file=sys.stderr)
				return True


# Starter
def main() -> int:
	"""Run the Mixtool application and return a status code."""
	
	# FIXME: Remove in final version
	print("Mixtool is running on Python {0[0]}.{0[1]} using PyGObject {1[0]}.{1[1]} and GTK+ {2[0]}.{2[1]}.".
		format(sys.version_info, gi.version_info, (Gtk.get_major_version(), Gtk.get_minor_version())), file=sys.stderr)
	
	# Initialize Application
	GLib.set_prgname("mixtool")
	GLib.set_application_name("Mixtool")
	application = Mixtool("com.bachsau.mixtool", Gio.ApplicationFlags.HANDLES_OPEN)
	
	# Start GUI
	# Since GTK+ does not support KeyboardInterrupt, reset SIGINT to default.
	# TODO: Build something with `GLib.unix_signal_add()`
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	status = application.run(sys.argv)
	print("GTK+ returned.", file=sys.stderr)
	
	return status


# A simple, instance-independent messagebox
def messagebox(text: str, type_: str = "i", parent: Gtk.Window = None, *, secondary: str = None, markup: int = 0) -> None:
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
		use_markup=bool(markup & 1),
		title=title,
		icon_name=icon,
		window_position=position,
		skip_taskbar_hint=skip_hint,
		skip_pager_hint=skip_hint,
		transient_for=parent
	)
	
	if secondary is not None:
		if markup & 2:
			dialog.format_secondary_markup(str(secondary))
		else:
			dialog.format_secondary_text(str(secondary))
	
	dialog.run()
	dialog.destroy()


# Run the application
sys.exit(main())
