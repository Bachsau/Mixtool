---
title: Using mixlib
canonical: mixlib.html
---

Using mixlib
=============

mixlib is the integral part of Mixtool which does all the background work of reading from and writing to MIX files. It is a Python 3 module developed together with Mixtool with reusability in mind. The plan is to move it to a separate package with the advent of Mixtool 1.0 and release it under the GNU Lesser General Public License, so it can be used by any other Python application that wants to work with MIX files.

I will try to keep mixlib as well documented as possible by using Python’s native capabilities like docstrings and function annotations, even for private methods. However, only the API described in this document and not prefixed with underscores should be considered public. Using private methods in third party applications is strongly discouraged and will most likely result in internal errors and corrupted files.


Getting started
----------------

Every MIX file is managed by an instance of mixlib.MixFile on top of a readable, buffered binary stream. This is what you get, when you call open() with one of the modes "rb" or "r+b".
