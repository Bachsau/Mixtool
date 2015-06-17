#!/usr/bin/python3

import os           as OS
#import signal       as Signal
#import sys          as Sys
#import threading    as Threading
#import time         as Time
#import configparser as ConfigParser

from gi.repository   import GObject, Gtk
import mixlib     as MixLib

# Handles all GUI commands
class GUIControlClass:
	# Constructor gets objects from GtkBuilder for interaction
	def __init__(self, GtkBuilder):
		self.MainWindow        = GtkBuilder.get_object("MainWindow")
		self.OpenDialog        = GtkBuilder.get_object("OpenDialog")
		self.SaveDialog        = GtkBuilder.get_object("SaveDialog")
		self.ExtractDialog     = GtkBuilder.get_object("ExtractDialog")
		self.SearchDialog      = GtkBuilder.get_object("SearchDialog")
		self.SearchDialogEntry = GtkBuilder.get_object("SearchDialogEntry")
		self.ContentStore      = GtkBuilder.get_object("ContentStore")
		self.StatusBar         = GtkBuilder.get_object("StatusBar")
		self.reset()
	
	# Reset GUI and close file
	def reset(self, *args):
		self.MixFile  = None
		self.unsaved  = False
		self.filename = ""
		self.ContentStore.clear()
		self.set_titlebar("Untitled")
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
		
		# List MIX content in Window
		for key, val in self.MixFile.contents.items():
			self.ContentStore.insert_with_valuesv(-1, (0, 1, 2, 3), (hex(key) if val["name"] is None else val["name"], val["size"] , val["offset"], val["index"]))
		
		self.set_titlebar(self.filename)
		self.set_statusbar(self.filename + " contains " + str(len(self.MixFile.contents)) + " files.")
			
	
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
		
	def searchdialog(self, *args):
		self.SearchDialogEntry.set_text("")
		self.SearchDialogEntry.grab_focus()
		response = self.SearchDialog.run()
		self.SearchDialog.hide()
		search = self.SearchDialogEntry.get_text()
		if response == Gtk.ResponseType.OK and search != "":
			messagebox(self.SearchDialogEntry.get_text(), "i", self.MainWindow)
		
		
			
	# Add content dialog
	def adddialog(self, *args):
		pass
		
	def set_statusbar(self, text):
		self.StatusBar.set_text(str(text))
		
	def set_titlebar(self, text):
		self.MainWindow.set_title(text + " – Mixtool")
		
	# Exit program
	def quit(self, *args):
		self.reset()
		Gtk.main_quit()
		print("GTK sauber beendet!")

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

# Main application
def main():
	# Create GtkBuilder and GUI controller
	GtkBuilder = Gtk.Builder()
	
	try:
		GtkBuilder.add_from_file("gui.glade")
	except GObject.GError:
		messagebox("Error reading GUI file", "e")
		raise
		
	GUIControl = GUIControlClass(GtkBuilder)
	GtkBuilder.connect_signals(GUIControl)
	
	# Start GUI
	Gtk.main()
	
if __name__ == "__main__": main()
