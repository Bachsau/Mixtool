#!/usr/bin/python3
# coding=utf8

import os           as OS
import locale       as Locale
import configparser as ConfigParser

from gi.repository  import GObject, Gdk, Gtk
import mixlib       as MixLib

# Constants
COLUMN_ROWID    = 0
COLUMN_NAME     = 1
COLUMN_OFFSET   = 2
COLUMN_SIZE     = 3
COLUMN_OVERHEAD = 4


# Global vars
windowlist = []
#settings   = {}

# Handles all GUI commands
class GUIController:
	# Read GUI from file and retrieve objects from GtkBuilder
	def __init__(self, filename, db):
		try:
			GtkBuilder = Gtk.Builder.new_from_file("gui.glade")
			GtkBuilder.connect_signals(self)
		except GObject.GError:
			messagebox("Error reading GUI file", "e")
			raise
			
		self.MainWindow        = GtkBuilder.get_object("MainWindow")
		self.OpenDialog        = GtkBuilder.get_object("OpenDialog")
		self.SaveDialog        = GtkBuilder.get_object("SaveDialog")
		self.ExtractDialog     = GtkBuilder.get_object("ExtractDialog")
		self.SearchDialog      = GtkBuilder.get_object("SearchDialog")
		self.SearchDialogEntry = GtkBuilder.get_object("SearchDialogEntry")
		self.AboutDialog       = GtkBuilder.get_object("AboutDialog")
		self.ContentList       = GtkBuilder.get_object("ContentList")
		self.ContentStore      = GtkBuilder.get_object("ContentStore")
		self.ContentSelector   = GtkBuilder.get_object("ContentSelector")
		self.StatusBar         = GtkBuilder.get_object("StatusBar")
		
		# Initially sort by Offset
		self.ContentStore.set_sort_column_id(COLUMN_OFFSET, Gtk.SortType.ASCENDING)
		
		if filename is not None:
			self.loadfile(filename)
		else:
			self.reset()
	
	# Reset GUI and close file
	def reset(self, *args):
		self.MixFile   = None
		self.filename  = "Untitled"
		self.contents  = {}
		self.ContentStore.clear()
		self.set_titlebar(self.filename)
		self.set_statusbar("This is alpha software. Use at your own risk!")
		
	# Load file
	def loadfile(self, filename):
		self.reset()
		
		# TODO: Input sanitising, test for existence
		try:
			self.MixFile = MixLib.MixFile(open(filename, "rb"))
		except Exception as error:
			messagebox("Error loading MIX file" ,"e")
			raise
		
		self.filename = OS.path.basename(filename)
		
		self.set_titlebar(self.filename)
		self.set_statusbar(" ".join((self.MixFile.get_type(), "MIX contains", str(self.MixFile.filecount), "files.")))
		
		for inode in self.MixFile.index:
			rowid = id(inode)
			treeiter = self.ContentStore.append((
				rowid,
				inode["name"],
				inode["offset"],
				inode["size"],
				inode["alloc"] - inode["size"]
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
	
	def savedialog(self, *args):
		response = self.SaveDialog.run()
		self.SaveDialog.hide()
		if response == Gtk.ResponseType.OK:
			messagebox("Selected " + self.SaveDialog.get_filename())
			
	def extractdialog(self, *args):
		selected = self.get_selected()
		filecount = len(selected)
		
		if filecount == 0:
			messagebox("Nothing selected", "e", self.MainWindow)
		else:
			if filecount > 1:
				self.ExtractDialog.set_action(Gtk.FileChooserAction.CREATE_FOLDER)
				self.ExtractDialog.set_current_name(self.filename.replace(".", "_"))
			else:
				key = selected[0]
				self.ExtractDialog.set_action(Gtk.FileChooserAction.SAVE)
				self.ExtractDialog.set_current_name(self.MixFile.contents[key]["name"] or hex(key))
				
			response = self.ExtractDialog.run()
			self.ExtractDialog.hide()
			
			if response == Gtk.ResponseType.OK:
				filename = self.ExtractDialog.get_filename()
				
				if filecount > 1:
					# Mitigate FileChoserDialog's incosistent behavior
					if OS.listdir(filename):
						filename += "/" + self.ExtractDialog.get_current_name()
						messagebox(filename)
						OS.mkdir(filename)
						
					# Save every file with its original name
					for key in selected:
						self.MixFile.extract(key, filename + "/" + (self.MixFile.contents[key]["name"] or hex(key)))
				else:
					self.MixFile.extract(selected[0], filename)
			
	def get_selected(self, *args):
		keylist = []
		rowlist = self.ContentSelector.get_selected_rows()
		for row in rowlist[1]:
			treeiter = self.ContentStore.get_iter(row)
			keylist.append(self.ContentStore[treeiter][COLUMN_KEY])
		return keylist
		
		
	def propertiesdialog(self, *args):
		messagebox("Not implemented yet", "i", self.MainWindow)
		
	def settingsdialog(self, *args):
		messagebox("Not implemented yet", "i", self.MainWindow)
		
	def aboutdialog(self, *args):
		self.AboutDialog.run()
		self.AboutDialog.hide()
		
	# Search current file for names
	def searchdialog(self, *args):
		if self.MixFile is not None:
			self.SearchDialogEntry.grab_focus()
			self.SearchDialogEntry.select_region(0, -1)
			response = self.SearchDialog.run()
			self.SearchDialog.hide()
			search = self.SearchDialogEntry.get_text()
		
			if response == Gtk.ResponseType.OK  and search != "":
				name  = self.SearchDialogEntry.get_text()
				key = self.MixFile.get_key(name)
			
				if key in self.contents:
					self.ContentStore[self.contents[key]][COLUMN_NAME] = self.MixFile.contents[key]["name"]
				
					path = self.ContentStore.get_path(self.contents[key])
					self.ContentList.set_cursor(path)
				else:
					messagebox(hex(key) + "not found in current mix", "i", self.MainWindow)
		else:
			messagebox("Search needs an open file", "e", self.MainWindow)
				
				
	# Add content dialog
	def adddialog(self, *args):
		pass
		
	def set_statusbar(self, text):
		self.StatusBar.set_text(str(text))
		
	def set_titlebar(self, text):
		self.MainWindow.set_title(text + " – Mixtool (Alpha)")
		
	# Close window / Exit program
	def quit(self, *args):
		global windowlist
		self.reset()
		self.MainWindow.destroy()
		windowlist.remove(self)
		if len(windowlist) < 1: Gtk.main_quit()

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
	
# Initiliaze GtkBuilder and GUI controller
def open_window(filename=None, db=None):
	global windowlist
	windowlist.append(GUIController(filename, db))
	
# Main application
def main():
	# Keep GTK+ from mixing languages
	Locale.setlocale(Locale.LC_ALL, "C")
	
	# Open first window
	open_window()
		
	# Start GUI
	Gtk.main()
	
	print("GTK quit cleanly")
	
if __name__ == "__main__": main()
