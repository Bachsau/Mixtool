Mixtool
========

An editor for Westwood Studios' MIX files, the data containers used in their classic Command & Conquer games from Tiberian Dawn to Red Alert 2: Yuri's Revenge.

Many thanks to Olaf van der Spek for his documentation of the MIX file format and the [XCC Utilities](http://xhp.xwis.net/).

**WARNING:** This is alpha software. Most functions won't work as expected and it may destroy the files you open with it! Use at your own risk and always have a backup at hand.


Features planned for the final version:
----------------------------------------

* Reading from and writing to all MIX files compatible with TD, RA and TS. Maybe RG.
* Creation of new files in all of these formats.
* In-place editing of all files contained in a MIX file.
* Live conversion between all supported formats.
* Full recursion for MIX files contained in other ones, including editing capabilities.
* Integrated online names database to avoid stumbling upon unknown filenames ever again.
* Interactive command line version
* Re-usable abstraction module to work with MIX files from any Python 3 application.
* Optimized, fast and beautiful code.
* Binary packages for Windows, Linux and macOS.


Features NOT to expect:
------------------------
* Integrated viewers for Westwood file formats often found inside MIX files.
* BIG file support
