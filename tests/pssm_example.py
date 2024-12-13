"""
A minimal working example for pssm. Can be run by itself, or by calling `run()`
File needs to be put outside the pssm module folder.
"""

print("Welcome to the PythonScreenStackManager (pssm) example.")

import PythonScreenStackManager as PSSM
from PythonScreenStackManager.devices import windowed
from PythonScreenStackManager import elements, pssm_types, pssm

device = windowed.Device(resizeable=True)

def change_text(element: elements.Element, coordinates: pssm_types.CoordType):
    #The button element defined below is passed as element. The x,y coordinates are passed as coordinates.
    #Since this is a minimal example, this function is not async, but pssm supports both coroutines and normal callables as tap_action.
    print(f"Clicked on element {element}")
    new_text = f"You clicked on x: {coordinates[0]} y: {coordinates[1]}"
    element.update({"text": new_text})

screen = pssm.PSSMScreen(device)

#Most base elements can be set up before defining the screen.
#However, more complex ones may need to have a screen instance defined. This is done when calling pssm.get_screen below
#In general, I would advise setting the screen first, and in, for example, a different file, define your main layout and importing the screen using `get_screen`.
#So similar to using tkinter, where you generally start off with defining the root window
button = elements.Button("Welcome to pssm", background_color="grey", tap_action=change_text, id="test-button")
layout = [["?"],["H*0.5", (None,"?"), (button, "W*0.5"), (None,"?")],["?"]]
layout = elements.Layout(layout)

screen.add_element(layout)

if __name__ == "__main__":
    screen.start_screen_printing()