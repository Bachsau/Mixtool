#!/usr/bin/python3
# coding=utf8

# Mixtool – An editor for Westwood Studios’ MIX files
# Copyright (C) 2015 Bachsau
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import sys          as Sys
import os           as OS
import locale       as Locale
import signal       as Signal
import configparser as ConfigParser

# Fix Glib segfaults
#OS.environ["G_SLICE"] = "always-malloc"

from gi.repository  import GObject, Gio, Gdk, Gtk
import mixlib       as MixLib

# Constants
COLUMN_ROWID    = 0
COLUMN_NAME     = 1
COLUMN_OFFSET   = 2
COLUMN_SIZE     = 3
COLUMN_OVERHEAD = 4

class Mixtool(Gtk.Application):
	"""Mixtool application management class"""
	__slots__ = "config", "conffile"
	
	def __init__(self, application_id, flags):
		"""Initialize GTK+ Application"""
		Gtk.Application.__init__(self, application_id=application_id, flags=flags)
		
		self.config = {}
		
		# Determine configuration file
		

	def do_activate(self, *args):
		"""Create a new main window"""
		MixWindow(self)
		
	def load_config(self):
		"""Load configuration from file"""
		
	def save_config(self):
		"""Save configuration to file"""
		
class MixWindow(object):
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
			self.MixFile = MixLib.MixFile(open(filename, "r+b"))
		except Exception as error:
			messagebox("Error loading MIX file" ,"e")
			raise

		self.filename = OS.path.basename(filename)

		self.set_titlebar(self.filename)
		self.set_statusbar(" ".join((self.MixFile.get_type(), "MIX contains", str(len(self.MixFile.contents)), "files.")))

		self.refresh()
			
	def refresh(self):
		self.contents  = {}
		self.ContentStore.clear()
		
		for inode in self.MixFile.contents:
			rowid = id(inode)
			treeiter = self.ContentStore.append((
				rowid,
				inode.name,
				inode.offset,
				inode.size,
				inode.alloc - inode.size
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
				filename = OS.path.basename(inpath)
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
					if OS.listdir(outpath):
						outpath = OS.path.join(outpath, Dialog.get_current_name())
						OS.mkdir(outpath)

					# Save every file with its original name
					for row in rows:
						filename = row[COLUMN_NAME]
						self.MixFile.extract(filename, OS.path.join(outpath, filename))
				else:
					self.MixFile.extract(filename, outpath)

	def get_selected_rows(self):
		rows = []
		for path in self.ContentSelector.get_selected_rows()[1]:
			rows.append(self.ContentStore[path])
		return rows

	def propertiesdialog(self, *args):
		messagebox("Not implemented yet", "i", self.MainWindow)

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
				inode = self.MixFile.get_inode(name)

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
			try: obj.destroy()
			except AttributeError: pass
			
# Starter
def main():
	# Keep GTK+ from mixing languages
	Locale.setlocale(Locale.LC_MESSAGES, "C")
	
	# Since GTK+ does not support KeyboardInterrupt, reset SIGINT to default.
	Signal.signal(Signal.SIGINT, Signal.SIG_DFL)
	
	# Initialize GObject's treads capability
	# Stops segfaults so G_SLICE="always-malloc" is not needed
	GObject.threads_init()
	
	# Initialize GTK Application // One window per process in alpha state
	GObject.set_application_name("Mixtool")
	Application = Mixtool("com.bachsau.mixtool", Gio.ApplicationFlags.NON_UNIQUE)
	
	# Start GUI
	status = Application.run()
	print("GTK returned")
	
	Sys.exit(status)

# A simple, instance-independant messagebox
def messagebox(text, type_="i", parent=None):
	if type_ == "e":
		message_type = Gtk.MessageType.ERROR
		buttons_type = Gtk.ButtonsType.OK
	else:
		message_type = Gtk.MessageType.INFO
		buttons_type = Gtk.ButtonsType.OK

	Dialog = Gtk.MessageDialog(parent, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, message_type, buttons_type, str(text))
	response = Dialog.run()
	Dialog.destroy()
	return response

if __name__ == "__main__": main()
