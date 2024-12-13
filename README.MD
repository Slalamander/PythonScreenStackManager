# Python Screen Stack Manager

Python Screen Stack Manager creates image based user interfaces by layering images. This means that in general, it is not the most efficient way of building an interface. However, it was originally designed to run on Kobo devices, which do not come with a window manager interface (At least that I know of). This means libraries like tkinter do not work, which is where pssm comes in. Since it simply generates images, as long as the device it is running on has a way to print pixel data onto the screen (and run Python code), it should be able to show pssm based interfaces.

The pip install does not come with this functionality however. It provides the bare bones to work with it, which in this case means a tkinter based window that prints the interface. PSSM is simply meant as the interface library. inkBoard (link coming) is meant to be the managing software integrating the devices.

It comes with a relatively robust set of premade elements, which can be used for a basic interface, however they can also be extended (for that, see the Home Assistant inkBoard integration, for example). You can also add the folders `/fonts`, `/icons` and `/pictures` to the directory you are running from, and when referencing a font for a button, for example, PSSM will look in that folder for the font file.

I have not done extensive testing with pssm outside of inkBoard, so I cannot promise everything will work standalone out of the box. This mainly pertains to instantiating various Elements which declare async classes inside their `__init__`, which may cause issues when no event loop is running yet. If you run into problems like this, please open an issue with the problematic element and the logs.

## Install
`pip install pssm`

# Documentation

WIP

# Examples

See `pssm_example.py`. This can also be run by invoking `python -m PythonScreenStackManager`. It runs the previously mentioned tkinter based interface, and provides a simply grey square that shows the coordinates you clicked on when interacting with it.