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
		self.MainWindow    = GtkBuilder.get_object("MainWindow")
		self.OpenDialog    = GtkBuilder.get_object("OpenDialog")
		self.SaveDialog    = GtkBuilder.get_object("SaveDialog")
		self.ExtractDialog = GtkBuilder.get_object("ExtractDialog")
		self.ContentStore  = GtkBuilder.get_object("ContentStore")
		self.StatusBar     = GtkBuilder.get_object("StatusBar")
		self.reset()
	
	# Reset GUI and close file
	def reset(self, *args):
		self.MixFile = None
		self.set_titlebar("Untitled")
		self.ContentStore.clear()
		
	# Load file
	def loadfile(self, filename):
		self.reset()
		
		# TODO: Input sanitising, test for existence
		try:
			self.MixFile = MixLib.MixFile(open(filename, "rb"))
		except Exception as error:
			dialogbox(error ,"e")
			raise
		
		self.set_titlebar(OS.path.basename(filename))
		
		# List MIX content in Window
		for key, val in self.MixFile.contents.items():
			self.ContentStore.insert_with_valuesv(-1, (0, 1, 2, 3), (hex(key) if val["name"] is None else val["name"], val["size"] , val["offset"], val["index"]))
		
			
		
	# Add file to mix
	def addfile(self, *args):
		pass
		
	# Remove content from mix
	def removeselected(self, *args):
		pass
	
	# Open dialog
	def opendialog(self, *args):
		response = self.OpenDialog.run()
		self.OpenDialog.hide()
		if response == Gtk.ResponseType.OK:
			self.loadfile(self.OpenDialog.get_filename())
	
	# Save dialog
	def savedialog(self, *args):
		response = self.SaveDialog.run()
		self.SaveDialog.hide()
		if response == Gtk.ResponseType.OK:
			dialogbox("Selected " + self.SaveDialog.get_filename())
			
	# Extract dialog
	def extractdialog(self, *args):
		dialogbox("Not implemented yet", "i", self.MainWindow)
		
	# Properties dialog
	def propertiesdialog(self, *args):
		dialogbox("Not implemented yet", "i", self.MainWindow)
		
	# Settings dialog
	def settingsdialog(self, *args):
		dialogbox("Not implemented yet", "i", self.MainWindow)
			
	# Add content dialog
	def adddialog(self, *args):
		pass
		
	def set_statusbar(self, text):
		self.StatusBar.set_text(str(text))
		
	def set_titlebar(self, text):
		self.MainWindow.set_title(text + " - Mixtool")
		
	# Exit program
	def quit(self, *args):
		self.reset()
		Gtk.main_quit()
		print("GTK sauber beendet!")

# A dialogbox for everything
def dialogbox(text, type="i", parent=None):
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
		dialogbox("Error reading GUI file", "e")
		raise
		
	GUIControl = GUIControlClass(GtkBuilder)
	GtkBuilder.connect_signals(GUIControl)
	
	# Start GUI
	Gtk.main()
	
if __name__ == "__main__": main()
