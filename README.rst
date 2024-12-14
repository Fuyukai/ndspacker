``ndspacker``
=============

``ndspacker`` is a wrapper tool used to build Nitro ROM files from an input ARM9 ELF and a donor
ARM7 file from an official ROM. 

Requirements
------------

- A copy of GCC binutils built with the prefix of ``arm-none-eabi-``, or LLVM binutils
- `ndstool <https://github.com/blocksds/ndstool>`_

At some point in the future these will be eliminated entirely and replaced with native parsing
and packing.

Usage
-----

Make an ``ndspacker.toml`` file in your project directory, with contents like so:

.. code-block:: toml

    # Arbitrary, two-letter code. Doesn't affect anything.
    maker_code = "01"

    # Arbitrary, four-byte code. This isn't used by anything except for identification.
    # First character can be A/B/C/T/Y (generic NDS game), D (DSi game)
    # Last character can be 'A' (for English), 'J' (for Japanese), or 'P' (Other)
    game_code = "ENAE"

    # Up to 12 bytes of ASCII for the game name. Doesn't affect anything.
    game_title = "ndspacker"

None of the actual values matter, they're just used for identifying your ROM in its header. Then,
run ``ndspacker <path to ARM9 elf> <path to ARM7 ROM or ELF>`` and it will spit out a ``rom.nds``
in the current directory.

Only ELF ARM9 images are supported, but for the ARM7 this can either be an ELF image or a donor
Nitro ROM to take the ARM7 from. If no ARM7 is specified, then a stub infinite loop ARM7 will be
included instead.

The ARM9 *must* be linked at the start of main memory i.e. ``0x2000000``. 
