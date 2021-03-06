﻿Mixtool
========

An editor for Westwood Studios’ MIX files, the data containers used in their
classic Command & Conquer games from “Tiberian Dawn” to “Renegade”.

Many thanks to Olaf van der Spek for his documentation of the MIX file format
and the [XCC Utilities][0].

**WARNING:** This is alpha software. Most functions won’t work as expected and
it may destroy the files you open with it! Use at your own risk and always have
a backup at hand.


Features planned for the final version:
----------------------------------------
* Reading from and writing to all MIX files compatible with TD, RA, TS,
  RA2 and RG
* Creation of new files in all of these formats
* In-place editing of all files contained in a MIX file
* Live conversion between all supported formats
* Recursive editing of MIX files contained in other ones
* Integrated online names database to avoid stumbling upon unknown filenames
  ever again
* Re-usable abstraction module to work with MIX files from any Python 3
  application  
  (Will be distributed under the MIT license)
* Optimized, fast and beautiful code
* Binary packages for Windows, Linux and macOS
* Integrated text editor


Features NOT to expect:
------------------------
* Integrated viewers for Westwood file formats often found inside MIX files
* BIG file support

[0]: http://xhp.xwis.net/
