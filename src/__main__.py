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

"""Mixtool GTK+ 3 application"""

__version__ = "0.2.0-volatile"
__author__ = "Bachsau"

# Standard modules
import sys
import os
import io
import collections
import collections.abc
import re
import signal
import random
import uuid
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
FileRecord = collections.namedtuple("FileRecord", ("path", "stat", "container", "store", "button", "existed"))


# A simple abstraction of Python's ConfigParser.
# It features implicit type conversion and defaults through prior
# registration of settings. It can be used to save and read settings
# without bothering about the specifics of ConfigParser or the INI files
# themselves. It could also serve as a starting point to abstract
# platform-specific saving methods through its general API.
class Configuration(collections.abc.MutableMapping):
	"""INI file based configuration manager"""
	
	__slots__ = ("_defaults", "_parser", "_section")
	
	key_chars = re.compile("[0-9_a-z]*", re.ASCII)
	
	def __init__(self, product: str) -> None:
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
		self._section = product
		self._parser.add_section(product)
	
	def __getitem__(self, identifier: str):
		"""Return value of `identifier` or the registered default on errors.
		
		KeyError is raised if there is no such identifier.
		"""
		default = self._defaults[identifier]
		if self._parser.has_option(self._section, identifier):
			dtype = type(default)
			try:
				if dtype is bool:
					return self._parser.getboolean(self._section, identifier)
				if dtype is int:
					return self._parser.getint(self._section, identifier)
				if dtype is float:
					return self._parser.getfloat(self._section, identifier)
				if dtype is str:
					return parse.unquote(self._parser.get(self._section, identifier), errors="strict")
				if dtype is bytes:
					return parse.unquote_to_bytes(self._parser.get(self._section, identifier))
			except ValueError:
				self._parser.remove_option(self._section, identifier)
		return default
	
	def __setitem__(self, identifier: str, value) -> None:
		"""Set `identifier` to `value`.
		
		KeyError is raised if `identifier` was not registered.
		TypeError is raised if `value` does not match the registered type.
		"""
		dtype = type(self._defaults[identifier])
		if dtype is bool and type(value) is bool:
			self._parser.set(self._section, identifier, "yes" if value else "no")
		elif dtype is int and type(value) is int\
		  or dtype is float and type(value) is float:
			self._parser.set(self._section, identifier, str(value))
		elif dtype is str and type(value) is str:
			self._parser.set(self._section, identifier, parse.quote(value))
		elif dtype is bytes and type(value) is bytes:
			self._parser.set(self._section, identifier, parse.quote_from_bytes(value))
		else:
			raise TypeError("Not matching registered type")
	
	def __delitem__(self, identifier: str) -> None:
		"""Remove customized value of `identifier`.
		
		Nothing is done if the value was not customized,
		but KeyError is raised if `identifier` was not registered."""
		if identifier in self._defaults:
			self._parser.remove_option(self._section, identifier)
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
		for identifier in self._defaults.keys():
			self._parser.remove_option(self._section, identifier)
	
	def register(self, identifier: str, default) -> None:
		"""Register a setting and its default value.
		
		Identifiers must consist of only lowercase letters,
		digits and underscores.
		
		The type of `default` also specifies the type returned later
		and what can be assigned.
		
		Supported types are bool, int, float, str, and bytes.
		"""
		if type(identifier) is not str:
			raise TypeError("Identifiers must be strings")
		if not identifier:
			raise ValueError("Identifiers must not be empty")
		if not self.key_chars.fullmatch(identifier):
			raise ValueError("Identifier contains invalid characters")
		if identifier in self._defaults:
			raise ValueError("Identifier already registered")
		if type(default) not in (bool, int, float, str, bytes):
			raise TypeError("Unsupported type")
		self._defaults[identifier] = default
	
	def get_default(self, identifier: str):
		"""Return the default value of `identifier`.
		
		KeyError is raised if there is no such identifier.
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


class Mixtool(Gtk.Application):
	"""Main application controller"""
	
	# Characters allowed when simple names are enforced
	simple_chars = re.compile("[-.\\w]*", re.ASCII)
	
	# The GtkFileFilter used by open/save dialogs
	file_filter = Gtk.FileFilter()
	file_filter.set_name("MIX files")
	file_filter.add_pattern("*.[Mm][Ii][Xx]")
	
	# Object initializer
	def __init__(self) -> None:
		"""Initialize the application controller."""
		Gtk.Application.__init__(
			self,
			application_id="com.bachsau.mixtool",
			flags=Gio.ApplicationFlags.HANDLES_OPEN
		)
		self.set_resource_base_path(None)
		
		# Initialize mandatory attributes
		self._data_path_blocked = False
		self._files = []
	
	# This is run when Gtk.Application initializes the first instance.
	# It is not run on any remote controllers.
	def do_startup(self) -> None:
		"""Set up the application."""
		Gtk.Application.do_startup(self)
		Gdk.Screen.get_default().set_resolution(96.0)
		
		# Parse GUI file
		app_path = os.path.dirname(os.path.realpath(__file__))
		gui_file = os.sep.join((app_path, "res", "main.glade"))
		self._builder = Gtk.Builder.new_from_file(gui_file)
		self._builder.connect_signals({
			"on_new_clicked": self.invoke_new_dialog,
			"on_open_clicked": self.invoke_open_dialog,
			"on_properties_clicked": self.invoke_properties_dialog,
			"on_optimize_clicked": noop,
			"on_insert_clicked": noop,
			"on_delete_clicked": self.delete_selected_files,
			"on_extract_clicked": self.invoke_extract_dialog,
			"on_settings_clicked": self.invoke_settings_dialog,
			"on_about_clicked": self.invoke_about_dialog,
			"on_close_clicked": self.close_current_file,
			"on_quit_clicked": self.close_window,
			"on_version_changed": self.update_properties_dialog,
			"on_defaults_clicked": self.restore_default_settings,
			"on_donate_clicked": self.open_donation_website,
			"on_selection_changed": self.handle_selection_change,
			"on_key_pressed": self.handle_custom_keys
		})
		
		# Determine platform-specific conditions
		self.home_path = os.path.realpath(os.path.expanduser("~"))
		if sys.platform.startswith("win"):
			# Microsoft Windows
			os_appdata = os.environ.get("APPDATA")
			if os_appdata is None:
				self.data_path = self.home_path + "\\AppData\\Roaming\\Bachsau\\Mixtool"
			else:
				self.data_path = os.path.realpath(os_appdata) + "\\Bachsau\\Mixtool"
			del os_appdata
			self._reserved_filenames = frozenset((
				"AUX", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7",
				"COM8", "COM9", "CON", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5",
				"LPT6", "LPT7", "LPT8", "LPT9", "NUL", "PRN"
			))
			self._reserved_filechars = re.compile("[\"*/:<>?\\\\|]|\\.$", re.ASCII)
		elif sys.platform.startswith("darwin"):
			# Apple macOS
			self.data_path = self.home_path + "/Library/Application Support/com.bachsau.mixtool"
			self._reserved_filenames = frozenset((".", ".."))
			self._reserved_filechars = re.compile("[/]", re.ASCII)
		else:
			# Linux and others
			os_appdata = os.environ.get("XDG_DATA_HOME")
			if os_appdata is None:
				self.data_path = self.home_path + "/.local/share/mixtool"
			else:
				self.data_path = os.path.realpath(os_appdata) + "/mixtool"
			del os_appdata
			self._reserved_filenames = frozenset((".", ".."))
			self._reserved_filechars = re.compile("[/]", re.ASCII)
		
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
				alert(
					"Mixtool was not able to create its data directory.", "w",
					secondary="{0}:\n{1}\n\n".format(problem_description, self.data_path)
					+ "Your settings will not be retained."
				)
		
		# Set path to configuration file
		self.config_file = os.sep.join((self.data_path, "settings.ini"))
		
		# Set up the configuration manager
		self.settings = Configuration("Mixtool")
		self.settings.register("version", "")
		self.settings.register("instid", 0)
		self.settings.register("simplenames", True)
		self.settings.register("insertlower", True)
		self.settings.register("decrypt", True)
		self.settings.register("backup", False)
		self.settings.register("extracttolast", True)
		self.settings.register("smalltools", False)
		self.settings.register("nomotd", False)
		self.settings.register("units", "iec")
		self.settings.register("mixdir", self.home_path)
		self.settings.register("extdir", self.home_path)
		self.settings.register("nowarn", 0)
		
		if not self._data_path_blocked:
			# Read configuration file
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
					problem_description = repr(problem)
				alert(
					"Mixtool is unable to read its configuration file.", "w",
					secondary="{0}:\n{1}\n\n".format(problem_description, self.data_path)
					+ "Your settings will be reset."
				)
			
			# Sanitize settings
			self.settings["version"] = __version__
			units = self.settings["units"]
			valunits = ("iec", "si", "none")
			if units not in valunits:
				units = units.lower()
				if units in valunits:
					self.settings["units"] = units
				else:
					del self.settings["units"]
			
			# Initialize the installation id
			# (to be used with online features)
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
		
		# Prepare GUI
		renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
		column = self._builder.get_object("ContentList.Name")
		column.pack_start(renderer, False)
		column.add_attribute(renderer, "text", 0)
		for column_id, data in (
			("ContentList.Size", 1),
			("ContentList.Offset", 2),
			("ContentList.Overhead", 3)
		):
			renderer = Gtk.CellRendererText(xalign=1.0, family="Monospace")
			column = self._builder.get_object(column_id)
			column.pack_start(renderer, False)
			column.set_cell_data_func(renderer, self._render_formatted_size, data)
		self.motd = random.choice((
			"CABAL is order",
			"Don’t throw stones in glass houses without proper protection",
			"For Kane",
			"If I am cut, do I not bleed?",
			"I’ve got a present for ya",
			"Kane lives in death",
			"Rubber shoes in motion",
			"The technology of peace",
			"Tiberium is the way and the life",
			"You can’t kill the messiah",
			"Your orders – My ideas"
		))
		self._apply_settings()
	
	def _apply_settings(self) -> None:
		"""Apply settings that should have an immediate effect on appearance."""
		self._builder.get_object("Toolbar").set_style(
			Gtk.ToolbarStyle.ICONS if self.settings["smalltools"] else Gtk.ToolbarStyle.BOTH
		)
		
		units = self.settings["units"]
		if units == "iec":
			self.size_units = (1024.0, ("B", "KiB", "MiB", "GiB", "TiB"))
		elif units == "si":
			self.size_units = (1000.0, ("B", "kB", "MB", "GB", "TB"))
		else:
			self.size_units = None
		
		if self._files:
			self._set_status(overhead=self._files[-1].container.get_overhead())
		else:
			self._set_status(None, None, None)
	
	def _set_status(self, text=Ellipsis, version=Ellipsis, overhead=Ellipsis) -> None:
		"""Update the specified fields of the status bar.
		
		Passing None sets the default *not-applicable* value.
		Passing ... does not change a fields current value.
		"""
		if text is not Ellipsis:
			label_widget = self._builder.get_object("StatusBar.Text")
			if text is None:
				label_widget.set_text(
					"Ready" if self.settings["nomotd"] else self.motd
				)
			else:
				label_widget.set_text(text)
		
		if version is not Ellipsis:
			label_widget = self._builder.get_object("StatusBar.Version")
			if version is None:
				label_widget.set_text("–")
			else:
				label_widget.set_text(version.name)
			label_widget.set_has_tooltip(version is mixlib.Version.TS)
		
		if overhead is not Ellipsis:
			label_widget = self._builder.get_object("StatusBar.Overhead")
			if overhead:
				label_widget.set_text(self._format_size(overhead) + " overhead")
				label_widget.set_has_tooltip(True)
			else:
				if overhead is None:
					label_widget.set_text("–")
				else:
					label_widget.set_text("No overhead")
				label_widget.set_has_tooltip(False)
	
	def invoke_properties_dialog(self, widget: Gtk.Widget) -> None:
		"""Show a dialog to modify the current file’s properties."""
		container = self._files[-1].container
		verstr = container.get_version().name
		version_chooser = self._builder.get_object("Properties.Version")
		version_chooser.set_active_id(verstr)
		self.update_properties_dialog(version_chooser)
		self._builder.get_object("PropertiesDialog.OK").grab_focus()
		dialog = self._builder.get_object("PropertiesDialog")
		response = dialog.run()
		dialog.hide()
		
		if response == Gtk.ResponseType.OK:
			newver = version_chooser.get_active_id()
			if newver != "TD":
				container.has_checksum = self._builder.get_object("Properties.Checksum").get_active()
				container.is_encrypted = self._builder.get_object("Properties.Encrypt").get_active()
			if newver != verstr:
				alert("Conversion is not implemented yet.", "e", widget.get_toplevel())
				# FIXME: Catch errors
				#container.convert(getattr(mixlib.Version, newver))
	
	def update_properties_dialog(self, version_chooser: Gtk.ComboBoxText) -> None:
		"""Update the properties dialog to reflect the chosen version."""
		container = self._files[-1].container
		decrypt = self.settings["decrypt"]
		checkbox_encrypted = self._builder.get_object("Properties.Encrypt")
		checkbox_checksum = self._builder.get_object("Properties.Checksum")
		
		if version_chooser.get_active_id() == "TD":
			checkbox_checksum.set_sensitive(False)
			checkbox_checksum.set_active(False)
			checkbox_encrypted.set_sensitive(False)
			checkbox_encrypted.set_active(False)
			checkbox_encrypted.set_has_tooltip(False)
		else:
			checkbox_checksum.set_sensitive(True)
			checkbox_checksum.set_active(container.has_checksum)
			checkbox_encrypted.set_sensitive(not decrypt)
			checkbox_encrypted.set_active(container.is_encrypted)
			checkbox_encrypted.set_has_tooltip(decrypt)
	
	def invoke_settings_dialog(self, widget: Gtk.Widget) -> None:
		"""Show a dialog with current settings and save any changes."""
		# The updater returns a tuple of checkboxes to not repeat
		# ourselfs when it comes to saving
		checkboxes = self._update_settings_dialog(False)
		self._builder.get_object("SettingsDialog.OK").grab_focus()
		dialog = self._builder.get_object("SettingsDialog")
		response = dialog.run()
		dialog.hide()
		
		if response == Gtk.ResponseType.OK:
			# Save new settings
			for checkbox, setting in checkboxes:
				self.settings[setting] = checkbox.get_active()
			self.settings["units"] = self._builder.get_object("Settings.Units").get_active_id()
			if self._builder.get_object("Settings.ResetWarnings").get_active():
				del self.settings["nowarn"]
			self._apply_settings()
			self._save_settings()
	
	def restore_default_settings(self, widget: Gtk.Widget) -> None:
		"""Set all widgets in the settings dialog to reflect the defaults."""
		self._update_settings_dialog(True)
	
	def _update_settings_dialog(self, defaults: bool) -> tuple:
		"""Populate the settings dialog with the current or default settings."""
		checkboxes = (
			(self._builder.get_object("Settings.SimpleNames"), "simplenames"),
			(self._builder.get_object("Settings.InsertLower"), "insertlower"),
			(self._builder.get_object("Settings.Decrypt"), "decrypt"),
			(self._builder.get_object("Settings.Backup"), "backup"),
			(self._builder.get_object("Settings.ExtractToLast"), "extracttolast"),
			(self._builder.get_object("Settings.SmallTools"), "smalltools"),
			(self._builder.get_object("Settings.DisableMOTD"), "nomotd")
		)
		units_dropdown = self._builder.get_object("Settings.Units")
		
		# Push current settings to dialog
		self._builder.get_object("Settings.ExtractToSource").set_active(True)
		self._builder.get_object("Settings.ResetWarnings").set_active(defaults)
		if defaults:
			for checkbox, setting in checkboxes:
				checkbox.set_active(self.settings.get_default(setting))
			units_dropdown.set_active_id(self.settings.get_default("units"))
		else:
			for checkbox, setting in checkboxes:
				checkbox.set_active(self.settings[setting])
			units_dropdown.set_active_id(self.settings["units"])
		
		# Return the tuple of checkboxes to be used for saving
		return checkboxes
	
	def _close_file(self, index: int) -> None:
		"""Close the file specified by `index`."""
		record = self._files.pop(index)
		record.container.finalize().close()
		record.button.destroy()
		
		if not record.stat.st_size:
			# File was initially empty, means it was created by Mixtool.
			try:
				stat = os.stat(record.path)
				if not stat.st_size and os.path.samestat(stat, record.stat):
					# File is still empty, so remove it.
					os.remove(record.path)
					if record.existed:
						# `existed` means something was there before.
						os.rename(record.path + ".bak", record.path)
			except OSError:
				pass
	
	def close_current_file(self, widget: Gtk.Widget) -> None:
		"""Close the currently active file."""
		self._close_file(-1)
		self._update_gui()
	
	# This method is labeled as "Quit" in the GUI,
	# because it is the ultimate result.
	def close_window(self, widget: Gtk.Widget, event: Gdk.Event = None) -> bool:
		"""Close the application window."""
		window = widget.get_toplevel()
		
		while(self._files):
			self._close_file(-1)
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
	
	def invoke_about_dialog(self, widget: Gtk.Widget) -> None:
		"""Display a dialog with information on Mixtool."""
		dialog = self._builder.get_object("AboutDialog")
		dialog.get_widget_for_response(Gtk.ResponseType.DELETE_EVENT).grab_focus()
		dialog.run()
		dialog.hide()
	
	def open_donation_website(self, widget: Gtk.Widget) -> None:
		"""Open donation website in default browser."""
		Gtk.show_uri_on_window(
			widget.get_toplevel(),
			"http://go.bachsau.com/mtdonate",
			Gtk.get_current_event_time()
		)
	
	def _get_fallback_directory(self, path: str) -> str:
		"""Return the deepest accessible directory of `path`."""
		if not os.path.isabs(path):
			path = self.home_path
		else:
			path = os.path.normpath(path)
		
		while not (os.access(path, 5) and os.path.isdir(path)):
			ppath = os.path.dirname(path)
			if ppath == path:
				break
			path = ppath
		
		return path
	
	def _get_selected_names(self):
		"""Return a list of all names selected by the user."""
		store, rows = self._builder.get_object("ContentSelector").get_selected_rows()
		return [store[treepath][0] for treepath in rows]
	
	def delete_selected_files(self, widget: Gtk.Widget) -> None:
		"""Delete selected files after showing an optional warning."""
		nowarn = self.settings["nowarn"]
		if not nowarn & 2:
			self._builder.get_object("DeletionWarning.Yes").grab_focus()
			dialog = self._builder.get_object("DeletionWarning")
			response = dialog.run()
			dialog.hide()
			if response != Gtk.ResponseType.YES:
				return
			if self._builder.get_object("DeletionWarning.Disable").get_active():
				self.settings["nowarn"] = nowarn | 2
				self._save_settings()
		
		self._check_make_backup()
		record = self._files[-1]
		names = self._get_selected_names()
		for filename in names:
			# FIXME: Add error handling
			record.container.delete(filename)
		# TODO: Save index
		self._reload_contents()
	
	def _adapt_filenames(self, names: list) -> list:
		"""Return a list of names changed to comply with local file system rules."""
		adapted_names = []
		for name in names:
			if name.upper() in self._reserved_filenames:
				adapted_name = "_" + name
			else:
				adapted_name = self._reserved_filechars.sub("_", name)
			if adapted_name in adapted_names:
				name_base, name_ext = splitext(adapted_name)
				adapted_name = name_base + "1" + name_ext
				i = 1
				while adapted_name in adapted_names:
					i += 1
					adapted_name = name_base + str(i) + name_ext
			adapted_names.append(adapted_name)
		return adapted_names
	
	def _format_size(self, value: int) -> str:
		"""Convert `value` to a human-readable size string."""
		if self.size_units is None:
			return str(value)
		base, units = self.size_units
		maxdim = len(units) - 1
		curdim = 0
		while value >= base and curdim < maxdim:
			curdim += 1
			value /= base
		fstring = "{0:.2f} {1}" if curdim else "{0:d} {1}"
		return fstring.format(value, units[curdim])
	
	def _render_formatted_size(
		self,
		column: Gtk.TreeViewColumn,
		renderer: Gtk.CellRendererText,
		tree_model: Gtk.TreeModel,
		tree_iter: Gtk.TreeIter,
		data: int
	) -> None:
		"""Set text of `renderer` to a size in a human-readable format."""
		value = tree_model.get_value(tree_iter, data)
		renderer.set_property("text", self._format_size(value))
	
	def invoke_extract_dialog(self, widget: Gtk.Widget, *junk) -> None:
		"""Show a file chooser dialog and extract selected files."""
		window = widget.get_toplevel()
		record = self._files[-1]
		etl = self.settings["extracttolast"]
		saved_path = self.settings["extdir"] if etl else os.path.dirname(record.path)
		browse_path = self._get_fallback_directory(saved_path)
		names = self._get_selected_names()
		multi = len(names) > 1
		if multi:
			adapted_names = [nt for nt in zip(names, self._adapt_filenames(names))]
			adaption_changes = [nt for nt in adapted_names if nt[0] != nt[1]]
			if adaption_changes:
				if len(adaption_changes) == 1:
					msg_title = "The following filename will be adjusted due to operating system’s limitations:"
				else:
					msg_title = "The following filenames will be adjusted due to operating system’s limitations:"
				msg_lines = []
				for source_name, dest_name in adaption_changes:
					msg_lines.append(source_name + "\xa0→\xa0" + dest_name)
				msg_text = "\n".join(msg_lines)
				alert(msg_title, "i", window, secondary=msg_text)
			dialog = Gtk.FileChooserDialog(
				title="Extract multiple files",
				transient_for=window,
				action=Gtk.FileChooserAction.SELECT_FOLDER
			)
		else:
			suggestion = names[0].replace(os.sep, "_")
			if os.path.lexists(os.sep.join((browse_path, suggestion))):
				name_base, name_ext = splitext(suggestion)
				suggestion = name_base + "1" + name_ext
				i = 1
				while os.path.lexists(os.sep.join((browse_path, suggestion))):
					i += 1
					suggestion = name_base + str(i) + name_ext
			dialog = Gtk.FileChooserDialog(
				title="Extract single file",
				transient_for=window,
				action=Gtk.FileChooserAction.SAVE
			)
			dialog.set_current_name(suggestion)
		dialog.add_buttons(
			"_Cancel", Gtk.ResponseType.CANCEL,
			"_Extract", Gtk.ResponseType.ACCEPT
		)
		try:
			while True:
				dialog.set_current_folder(browse_path)  # Weird but necessary ↓
				response = dialog.run()
				dialog.hide()
				if response != Gtk.ResponseType.ACCEPT:
					return
				browse_path = dialog.get_current_folder()  # Weird but necessary ↑
				destpath = dialog.get_filename()
				if not multi:
					# FIXME: Test filename validity here
					pass
				if ask("The following files already exist in\n" + browse_path + ":", "yn", window, secondary="These files will be overwritten. Is that OK?"):
					# FIXME: Test and build nice message
					break
			
			if etl:
				# Save last used directory
				if browse_path != saved_path:
					self.settings["extdir"] = browse_path
					self._save_settings()
			
			# Extract the files
			curdest = destpath
			self.mark_busy()
			try:
				for filename in names:
					if multi:
						# FIXME: Use adapted_names
						curdest = os.sep.join((destpath, filename))
					try:
						record.container.extract(filename, curdest)
					except Exception:
						# TODO: Do error handling
						raise
			finally:
				self.unmark_busy()
		finally:
			dialog.destroy()
	
	# Callback to create a new file by using a dialog
	def invoke_new_dialog(self, widget: Gtk.Widget) -> None:
		"""Show a file chooser dialog and create a new file."""
		window = widget.get_toplevel()
		saved_path = self.settings["mixdir"]
		browse_path = self._get_fallback_directory(saved_path)
		name_base = "new"
		name_ext = ".mix"
		suggestion = name_base + name_ext
		i = 0
		while os.path.lexists(os.sep.join((browse_path, suggestion))):
			i += 1
			suggestion = name_base + str(i) + name_ext
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
			dialog.set_current_name(suggestion)
			response = dialog.run()
			dialog.hide()
			if response == Gtk.ResponseType.ACCEPT:
				# Save last used directory
				browse_path = dialog.get_current_folder()
				if browse_path != saved_path:
					self.settings["mixdir"] = browse_path
					self._save_settings()
				
				# Open the files
				version = getattr(mixlib.Version, version_chooser.get_active_id())
				self._open_files(dialog.get_files(), version)
		finally:
			dialog.destroy()
	
	# Callback to open files by using a dialog
	def invoke_open_dialog(self, widget: Gtk.Widget) -> None:
		"""Show a file chooser dialog and open selected files."""
		window = widget.get_toplevel()
		saved_path = self.settings["mixdir"]
		browse_path = self._get_fallback_directory(saved_path)
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
					self.settings["mixdir"] = browse_path
					self._save_settings()
				
				# Open the files
				self._open_files(dialog.get_files())
		finally:
			dialog.destroy()
	
	def _reload_contents(self) -> None:
		"""Refresh contents from container data."""
		record = self._files[-1]
		record.store.clear()
		for content in record.container.get_contents():
			record.store.append((
				content.name,
				content.size,
				content.offset,
				content.alloc - content.size
			))
	
	def _check_make_backup(self) -> bool:
		"""Backup the current file if backups are enabled and none exists.
		
		Return False to abort pending operations, else True.
		"""
		if self.settings["backup"]:
			record = self._files[-1]
			bakpath = record.path + ".bak"
			if record.existed and not os.path.lexists(bakpath):
				instream = record.container._stream
				orgpos = instream.tell()
				remaining = instream.seek(0, io.SEEK_END)
				try:
					if remaining:
						instream.seek(0)
					else:
						return True
					# FIXME: Add error handling
					with open(bakpath, "wb") as outstream:
						buflen = min(remaining, mixlib.BLOCKSIZE)
						buffer = memoryview(bytearray(buflen))
						while remaining >= buflen:
							remaining -= instream.readinto(buffer)
							outstream.write(buffer)
						if remaining:
							buffer = buffer[:remaining]
							instream.readinto(buffer)
							outstream.write(buffer)
						del buffer
				finally:
					instream.seek(orgpos)
		return True
	
	def _open_files(self, files: list, new: mixlib.Version = None) -> None:
		"""Open `files` and create a new tab for each one."""
		window = self.get_active_window()
		backup = self.settings["backup"]
		fd_support = os.stat in os.supports_fd
		errors = []
		
		self.mark_busy()
		try:
			button = self._files[-1].button if self._files else None
			for file in files:
				path = os.path.realpath(file.get_path())
				stat = None
				
				# Check if file exists
				try:
					stat = os.stat(path)
				except OSError as problem:
					if new is None or not isinstance(problem, FileNotFoundError):
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
						existed = False
						stream = open(path, "w+b")
					else:
						existed = True
						if new is None or not backup:
							stream = open(path, "r+b")
						else:
							bakpath = path + ".bak"
							if os.path.lexists(bakpath):
								stream = open(path, "r+b")
							else:
								os.rename(path, bakpath)
								stream = open(path, "w+b")
					# Stat real file (not racy if `fd_support` is True)
					stat = os.stat(stream.fileno() if fd_support else path)
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
						for content in container.get_contents():
							store.append((
								content.name,
								content.size,
								content.offset,
								content.alloc - content.size
							))
						
						# Add a button
						button = Gtk.RadioButton.new_with_label_from_widget(button, os.path.basename(path))
						button.set_mode(False)
						button.get_child().set_ellipsize(Pango.EllipsizeMode.END)
						button.set_tooltip_text(path)
						self._builder.get_object("TabBar").pack_start(button, False, True, 0)
						button.show()
						
						# Create the file record
						record = FileRecord(path, stat, container, store, button, existed)
						self._files.append(record)
						
						# Connect the signal
						button.connect("toggled", self.switch_file, record)
					finally:
						if container is None:
							stream.close()
			
			if len(files) - len(errors):
				self._update_gui()
		finally:
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
			
			alert(err_title, "e", window, secondary=err_text, markup=2)
	
	# Switch to another tab
	def switch_file(self, button: Gtk.RadioButton, record: FileRecord) -> None:
		"""Switch the currently displayed file to `record`."""
		if button.get_active():
			self._files.remove(record)
			self._files.append(record)
			
			title = button.get_label() + " – Mixtool"
			self._builder.get_object("MainWindow").set_title(title)
			
			content_list = self._builder.get_object("ContentList")
			content_list.set_model(record.store)
			content_list.grab_focus()
	
	def _update_gui(self) -> None:
		"""Enable or disable GUI elements based on current state."""
		if self._files:
			# Switch to Close button and enable ContentList
			self._builder.get_object("Toolbar.Quit").hide()
			self._builder.get_object("Toolbar.Close").show()
			self._builder.get_object("Toolbar.Properties").set_sensitive(True)
			self._builder.get_object("ContentList").set_sensitive(True)
			
			# Switch to last open file
			button = self._files[-1].button
			button.toggled() if button.get_active() else button.set_active(True)
		else:
			# Switch to Quit button and disable ContentList
			self._builder.get_object("Toolbar.Close").hide()
			self._builder.get_object("Toolbar.Quit").show()
			self._builder.get_object("Toolbar.Properties").set_sensitive(False)
			self._builder.get_object("ContentList").set_sensitive(False)
			
			# Reverse what self.switch_file() does
			self._builder.get_object("MainWindow").set_title("Mixtool")
			dummy_store = self._builder.get_object("DummyStore")
			self._builder.get_object("ContentList").set_model(dummy_store)
			self._set_status(None, None, None)
		
		# Display tab bar only when two ore more files are open
		if len(self._files) < 2:
			self._builder.get_object("TabBar").hide()
		else:
			self._builder.get_object("TabBar").show()
	
	def handle_selection_change(self, selector: Gtk.TreeSelection) -> None:
		"""Toggle button sensitivity based on the current selection."""
		if self._files:
			record = self._files[-1]
			mixlen = record.container.get_filecount()
			selcount = selector.count_selected_rows()
			if selcount:
				status = "{0} files in MIX, {1} selected".format(mixlen, selcount)
				valid = True
			else:
				status = "{0} files in MIX".format(mixlen)
				valid = False
			self._set_status(status, record.container.get_version(), record.container.get_overhead())
		else:
			valid = False
		
		self._builder.get_object("Toolbar.Delete").set_sensitive(valid)
		self._builder.get_object("Toolbar.Extract").set_sensitive(valid)
	
	def handle_custom_keys(self, widget: Gtk.Widget, evkey: Gdk.EventKey) -> bool:
		"""React to pressing delete on the content list."""
		if evkey.keyval == Gdk.KEY_Delete:
			if not evkey.state & 13:
				self.delete_selected_files(widget)
			return True
		return False
	
	# Method run on the primary instance whenever the application
	# is invoked without parameters.
	def do_activate(self) -> None:
		"""Create a new main window or present an existing one."""
		window = self.get_active_window()
		if window is None:
			window = self._builder.get_object("MainWindow")
			self.add_window(window)
			window.show()
			
			nowarn = self.settings["nowarn"]
			if not nowarn & 1:
				self._builder.get_object("VersionWarning.OK").grab_focus()
				dialog = self._builder.get_object("VersionWarning")
				dialog.run()
				dialog.hide()
				if self._builder.get_object("VersionWarning.Disable").get_active():
					self.settings["nowarn"] = nowarn | 1
					self._save_settings()
		else:
			window.present()
			print("Activated main window on behalf of remote controller.", file=sys.stderr)
	
	# Method run on the primary instance whenever the application
	# is told to open files from outside.
	def do_open(self, files: list, *junk) -> None:
		"""Open `files` in a new or existing main window."""
		self.activate()
		self._open_files(files)
	
	def _save_settings(self) -> bool:
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
				
				alert(
					"Mixtool was not able to write its configuration file.", "w",
					secondary="{0}:\n{1}\n\n".format(problem_description, self.data_path)
					+ "Changed settings will not be retained."
				)
			else:
				print("Saved configuration file.", file=sys.stderr)
				return True
		return False


# Starter
def main() -> int:
	"""Run the Mixtool application and return a status code."""
	
	# Keep the app from crashing on legacy terminal encondings
	sys.stdout.reconfigure(errors="replace")
	sys.stderr.reconfigure(errors="replace")
	
	print("Mixtool is running on Python {0}.{1} using PyGObject {2}.{3} and GTK+ {4}.{5}.".
		format(
			sys.version_info[0],
			sys.version_info[1],
			gi.version_info[0],
			gi.version_info[1],
			Gtk.get_major_version(),
			Gtk.get_minor_version()
		), file=sys.stderr)
	
	# Initialize Application
	GLib.set_prgname("mixtool")
	GLib.set_application_name("Mixtool")
	application = Mixtool()
	
	# Start GUI
	# Since GTK+ does not support KeyboardInterrupt, reset SIGINT to default.
	# TODO: Build something with `GLib.unix_signal_add()`
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	status = application.run(sys.argv)
	print("GTK+ returned.", file=sys.stderr)
	
	return status


# A simple, instance-independent messagebox
def alert(text, severity: str = "i", parent: Gtk.Window = None, *, secondary=None, markup: int = 0) -> None:
	"""Display a dialog box containing `text` and an OK button.
	
	`severity` can be 'i' for info, 'w' for warning, or 'e' for error.
	
	If `parent` is given, the dialog will be a child of that window and
	centered upon it.
	
	`secondary` can be used to display additional text. The primary text
	will appear bolder in that case.
	"""
	if severity == "i":
		message_type = Gtk.MessageType.INFO
		title = "Notice"
		icon = "dialog-info"
	elif severity == "w":
		message_type = Gtk.MessageType.WARNING
		title = "Warning"
		icon = "dialog-warning"
	elif severity == "e":
		message_type = Gtk.MessageType.ERROR
		title = "Error"
		icon = "dialog-error"
	else:
		raise ValueError("Invalid severity level")
	
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


# Messageboxes for when the user has a choice
def ask(text, buttons: str = "yn", parent: Gtk.Window = None, *, secondary=None, markup: int = 0) -> bool:
	"""Display a dialog box containing `text` and two buttons.
	
	`buttons` can be 'yn' for Yes and No, or 'oc' for OK and Cancel.
	
	If `parent` is given, the dialog will be a child of that window and
	centered upon it.
	
	`secondary` can be used to display additional text. The primary text
	will appear bolder in that case.
	"""
	if buttons == "yn":
		buttons_type = Gtk.ButtonsType.YES_NO
		positive_response = Gtk.ResponseType.YES
	elif buttons == "oc":
		buttons_type = Gtk.ButtonsType.OK_CANCEL
		positive_response = Gtk.ResponseType.OK
	else:
		raise ValueError("Invalid buttons")
	
	if parent is None:
		position = Gtk.WindowPosition.CENTER
		skip_hint = False
	else:
		position = Gtk.WindowPosition.CENTER_ON_PARENT
		skip_hint = True
	
	dialog = Gtk.MessageDialog(
		message_type=Gtk.MessageType.QUESTION,
		buttons=buttons_type,
		text=str(text),
		use_markup=bool(markup & 1),
		title="Question",
		icon_name="dialog-question",
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
	
	response = dialog.run()
	dialog.destroy()
	return response == positive_response


def splitext(name: str) -> tuple:
	"""Split the extension from a filename."""
	dotpos = name.rfind(".")
	return (name[:dotpos], name[dotpos:]) if dotpos > 0 else (name, "")


def noop(*args) -> None:
	"""Do nothing."""


# Run the application
sys.exit(main())
