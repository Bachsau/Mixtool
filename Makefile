# This file will be used to compile l10n files and resource bundles,
# both of which are not implemented yet.
.ONESHELL:
	
.PHONY:all
	
all:src/gui.gresource
	
src/gui.gresource:src/gresource.xml $(shell glib-compile-resources '--sourcedir=src/res' '--generate-dependencies' 'src/gresource.xml')
	glib-compile-resources '--target=src/gui.gresource' '--sourcedir=src/res' 'src/gresource.xml'
