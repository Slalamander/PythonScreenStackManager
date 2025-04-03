"General Utils."

import inspect
from typing import (
    TypeVar,
    Generic,
    Callable,
    Any
)
import functools

T = TypeVar("T")
R = TypeVar("R")

class classproperty(Generic[T, R]):
    """Used to avoid the deprecation warning (and the extra writing) needed to set class properties
    
    To make them behave like property but on a class level, the class itself needs to have the metaclass ``ClassPropertyMetaClass`` from util.
    For elements this is not required, as it is handled in the base Element class, however in that case it does not prevent the attribute from being set via the class itself.
    """
    
    def __init__(self, fget: Callable[[type[T]], R], fset = None) -> R:
        self.fget = fget
        self.fset = fset
        functools.update_wrapper(self, wrapped=fget) # type: ignore

    def __get__(self, obj, cls= type[T]) -> R:
        if cls is None:
            cls = type(obj)
        return self.fget(cls)
    
    def __set__(self, obj, value):
        if not self.fset:
            raise AttributeError("can't set attribute")
        if inspect.isclass(obj):
            type_ = obj
            obj = None
        else:
            type_ = type(obj)
        return self.fset.__get__(obj, type_)(value)

    def setter(self, func):
        if not isinstance(func, (classmethod, staticmethod)):
            func = classmethod(func)
        self.fset = func
        return self


def isclassproperty(obj: Any, attr: str) -> bool:
    """Checks if the object's attribute is a classproperty

    Parameters
    ----------
    obj : Any
        The object the attribute belongs to. Can be a class or an instance of one
    attr : str
        The attribute to check

    Returns
    -------
    bool
        True if the attribute is a classproperty
    """

    
    if not inspect.isclass(obj):
        if not hasattr(obj, attr):
            return False
        cls = type(obj)
    else:
        cls = obj
        
        if attr in cls.__dict__:
            obj = cls.__dict__.get(attr)
            if isinstance(obj, classproperty):
                return True
        return False
    
    return False


class ClassPropertyMetaClass(type):
    
    def __setattr__(self, attr, value):

        if isclassproperty(self, attr):
            obj = self.__dict__.get(attr)
            return obj.__set__(self, value)

        return super(ClassPropertyMetaClass, self).__setattr__(attr, value)


class customproperty(property):
    "Base class for making custom property decorators."

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(obj)

    def __set__(self, obj, value):
        if self.fset is None:
            raise AttributeError("can't set attribute")
        self.fset(obj, value)

    def __delete__(self, obj):
        if self.fdel is None:
            raise AttributeError("can't delete attribute")
        self.fdel(obj)

    def getter(self, fget):
        return type(self)(fget, self.fset, self.fdel, self.__doc__)

    def setter(self, fset):
        return type(self)(self.fget, fset, self.fdel, self.__doc__)

    def deleter(self, fdel):
        return type(self)(self.fget, self.fset, fdel, self.__doc__)

##Tools to move: basically, anything that is so general it can be dropped in anywhere.
##Hence DummyTask and Singleton are not moved here since they are implemented deeper into pssm
##(DummyTask is debatable tbf)
##To move:
## - update_nested_dict
## - TypedDict_checker
## - iscoroutinefunction (from pssm.util)
## - wrap_to_coroutine
## - _block_run_coroutine
## - rotation_matrix
## - fit_Image (?)
