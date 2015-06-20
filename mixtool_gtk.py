#!/usr/bin/python3
# coding=utf8

import os           as OS
import configparser as ConfigParser

from gi.repository  import GObject, Gdk, Gtk
import mixlib       as MixLib

# Constants
COLUMN_NAME   = 0
COLUMN_SIZE   = 1
COLUMN_OFFSET = 2
COLUMN_KEY    = 3

# Global vars
windowlist = []
settings   = {}

# Handles all GUI commands
class GUIController:
	# Read GUI from file and retrieve objects from GtkBuilder
	def __init__(self, filename):
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
		self.ContentList       = GtkBuilder.get_object("ContentList")
		self.ContentStore      = GtkBuilder.get_object("ContentStore")
		self.StatusBar         = GtkBuilder.get_object("StatusBar")
		
		# Initially sort by Offset
		self.ContentStore.set_sort_column_id(COLUMN_OFFSET, Gtk.SortType.ASCENDING)
		
		if filename is not None:
			self.loadfile(filename)
		else:
			self.reset()
	
	# Reset GUI and close file
	def reset(self, *args):
		self.MixFile  = None
		self.unsaved  = False
		self.filename = "Untitled"
		self.contents = []
		self.ContentStore.clear()
		self.set_titlebar(self.filename)
		self.set_statusbar("This is alpha software. Use at your own risk!")
		
	# Load file
	def loadfile(self, filename):
		self.newfile()
		
		# TODO: Input sanitising, test for existence
		try:
			self.MixFile = MixLib.MixFile(open(filename, "rb"))
		except Exception as error:
			messagebox(error ,"e")
			raise
		
		self.filename = OS.path.basename(filename)
		
		games = "Tiberian Dawn", "Red Alert", "Tiberian Sun"
		mixtype = games[self.MixFile.get_type()]
		self.set_titlebar(self.filename)
		self.set_statusbar(" ".join((mixtype, "MIX contains", str(self.MixFile.filecount), "files.")))
		
		self.update_contents()
		
	# List MIX content in Window
	def update_contents(self, *args):
		self.contents = []
		self.ContentStore.clear()
		index = 0
		for content in self.MixFile.index:
			treeiter = self.ContentStore.insert_with_valuesv(-1,
				(COLUMN_NAME, COLUMN_SIZE, COLUMN_OFFSET, COLUMN_KEY),
				("(Unknown)" if content["name"] is None else content["name"], content["size"] , content["offset"], hex(content["key"])))
			
			self.contents.append(treeiter)
			
			index += 1
			
			
	def newfile(self, *args):
		if self.unsaved:
			# TODO: Ask user for saving
			if True: # User says yes
				# self.savedialog()
				# If user cancels saving: return
				pass
			elif False: # User cancels question
				return
			
		# File was saved or user choose not to save
		self.reset()
			
	
	# Add file to mix
	def addfile(self, *args):
		pass
		
	# Remove content from mix
	def removeselected(self, *args):
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
		messagebox("Not implemented yet", "i", self.MainWindow)
		
	def propertiesdialog(self, *args):
		messagebox("Not implemented yet", "i", self.MainWindow)
		
	def settingsdialog(self, *args):
		messagebox("Not implemented yet", "i", self.MainWindow)
		
	# Search current file for names
	def searchdialog(self, *args):
		self.SearchDialogEntry.grab_focus()
		self.SearchDialogEntry.select_region(0, -1)
		response = self.SearchDialog.run()
		self.SearchDialog.hide()
		search = self.SearchDialogEntry.get_text()
		
		if response == Gtk.ResponseType.OK  and search != "":
			name  = self.SearchDialogEntry.get_text()
			key = self.MixFile.get_key(name)
			inode = self.MixFile.get_inode(key)
			
			if inode is not None:
				self.ContentStore[self.contents[inode]][0] = self.MixFile.index[inode]["name"]
				
				path = self.ContentStore.get_path(self.contents[inode])
				self.ContentList.set_cursor(path)
			else:
				messagebox(self.filename + " does not cotain a file with key " + hex(key), "i", self.MainWindow)
				
				
	# Add content dialog
	def adddialog(self, *args):
		pass
		
	def set_statusbar(self, text):
		self.StatusBar.set_text(str(text))
		
	def set_titlebar(self, text):
		self.MainWindow.set_title(text + " – Mixtool")
		
	# Close window / Exit program
	def close(self, *args):
		global windowlist
		self.reset()
		self.MainWindow.destroy()
		windowlist.remove(self)
		if len(windowlist) < 1: Gtk.main_quit()

# A simple, instance-independant messagebox
def messagebox(text, type="i", parent=None):
	if type == "e":
		MessageType = Gtk.MessageType.ERROR
		ButtonsType = Gtk.ButtonsType.OK
	else:
		MessageType = Gtk.MessageType.INFO
		ButtonsType = Gtk.ButtonsType.OK
	
	dialogwidget = Gtk.MessageDialog(parent, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, MessageType, ButtonsType, str(text))
	response = dialogwidget.run()
	dialogwidget.destroy()
	return response
	
# Initiliaze GtkBuilder and GUI controller
def open_window(filename=None):
	global windowlist
	windowlist.append(GUIController(filename))
	
# Main application
def main():
	# Open first window
	open_window()
		
	# Start GUI
	Gtk.main()
	
	print("GTK quit cleanly")
	
if __name__ == "__main__": main()
