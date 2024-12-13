

class ReloadWarning(RuntimeWarning):
    """
    Exception Class for inkBoard. This exception can be caught out when awaiting the print loop, as it is set when calling reload.
    If not caught out, this simply means the screen will stop printing.
    """
    pass

class FullReloadWarning(ReloadWarning):
    """
    Indicates the user requested a full reload (instead of a 'normal' one). Implementation is up to the programme handling PSSM.
    """

class InteractionError(NotImplementedError):
    "The device does not support screen interaction."
    pass

class ElementRegisterError(KeyError):
    "Error with the element register. I.e. duplicate ID, or an ID could not be found."


class ElementNotRegistered(ElementRegisterError):
    """
    Raised when an element id is requested that is not registered.
    The missing id can be passed to quickly construct a useful error message. Optionally pass the parent element for more clarity. If passing message, the default message is not constructed.
    """
    def __init__(self, element_id: str = None, parent_elt = None, message = None):
        if message == None and element_id != None:
            message = f"No element with id {element_id} has been registered."
            if parent_elt != None: message = f"{parent_elt}: {message}"
        super().__init__(message)


class DuplicateElementError(ElementRegisterError):
    "Raised when an element is registered with an id that already exists."
    pass


class ShorthandNotFound(ValueError):
    "Raised when a requested shorthand is not found"
    def __init__(self, shorthand: str = "", msg: str = None):
        if not msg:
            msg = f"Could not find shorthand function identifier by {shorthand}"
        super().__init__(msg)
        ##How to get the message?

class ShorthandGroupNotFound(ShorthandNotFound):
    "Could not find a group belonging to the requested identifier"
    def __init__(self, identifier = "", msg: str = None):
        if not msg:
            msg = f"No function group with identifier {identifier} registered"
        ValueError().__init__(msg)