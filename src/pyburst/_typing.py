"""
Copyright (C) 2024 Riccardo Felicetti <https://github.com/Unoaccaso>

Created Date: Friday, February 9th 2024, 2:29:57 pm
Author: Riccardo Felicetti

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the
Free Software Foundation, version 3. This program is distributed in the hope
that it will be useful, but WITHOUT ANY WARRANTY; 
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR 
PURPOSE. See the GNU Affero General Public License for more details.
You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https: //www.gnu.org/licenses/>.
"""

from functools import wraps


import typing
import types

T = typing.TypeVar("T")


def _check_arg(arg, arg_type_hints):
    """
    Checks if an argument is an instance of one or more specified types.

    Args:
        arg: The argument to check.
        arg_type_hints: Type hints specifying the type(s) the argument should have.
            It can be a simple type or a composed type, such as a Union of types.

    Raises:
        TypeError: If the argument is not an instance of the specified type.
        NotImplementedError: If type checking for a certain type is not implemented.

    Examples:
        # Check if 'value' is an integer
        _check_arg(value, int)

        # Check if 'data' is a list of integers
        _check_arg(data, list[int])

        # Check if 'value' is either a string or an integer
        _check_arg(value, typing.Union[str, int])

        # Check if 'matrix' is a list of lists of integers
        _check_arg(matrix, list[list[int]])
    """
    type_error_msg = f"{arg} is not an instance of {arg_type_hints}"
    arg_type_origin = typing.get_origin(arg_type_hints)

    # Check for simple types
    if arg_type_origin is None:
        error_formats = [dict, list]
        if arg_type_hints in error_formats:
            raise NotImplementedError(
                f"Type checking for {arg_type_hints} not implemented"
            )
        if not isinstance(arg, arg_type_hints):
            raise TypeError(type_error_msg)

    # Check for composed types
    else:
        arg_types = typing.get_args(arg_type_hints)
        if arg_type_origin not in (typing.Union, types.UnionType):
            non_monadic = (
                any(typing.get_origin(_) for _ in arg_types) or len(arg_types) > 1
            )
            if non_monadic:
                raise NotImplementedError(
                    f"Type checking for {arg_type_hints} not implemented: Non monadic!"
                )
            # Checking if parent object is right
            if not isinstance(arg, arg_type_origin):
                raise TypeError(type_error_msg)
            if hasattr(arg, "dtype"):
                if arg.dtype not in arg_types:
                    raise TypeError(type_error_msg)
            elif isinstance(arg, list):
                if not all(isinstance(elem, arg_types) for elem in arg):
                    raise TypeError(type_error_msg)
            else:
                raise NotImplementedError(
                    f"Type checking for {arg_types} not implemented"
                )
        else:
            for arg_type in arg_types:
                try:
                    _check_arg(arg, arg_type)
                    break
                except TypeError:
                    continue
                except NotImplementedError as err:
                    raise err
            else:
                raise TypeError(type_error_msg)


def type_check(classmethod: bool = False) -> typing.Callable[..., T]:
    """
    Decorator that enforces strong typing for the arguments of a function based on type hints.

    Parameters
    ----------
    func : callable
        The function to be decorated.
    classmethod : bool
        Specifies if function is a classmethod.

    Returns
    -------
    callable
        A wrapper function that performs type checking before calling the original function.

    Raises
    ------
    AssertionError
        If any argument does not match its annotated type.

    Examples
    --------

    >>> from pyburst import type_check
    >>> @type_check
    ... def my_function(x: int, y: float):
    ...     return x + y
    >>> my_function(3, 4.5)  # No type errors
    7.5
    >>> my_function("a", 4.5)  # Raises AssertionError
    Traceback (most recent call last):
        ...
    AssertionError: a is not an instance of <class 'int'>

    It also supports numpy and cupy arrays

    >>> from numpy.typing import NDArray
    >>> from numpy import int32, float64
    >>> @type_check
    ... def my_function(x: NDArray[int32]):
    ...     pass
    >>> arr_int = numpy.array([1, 2, 3, 4], dtype = int32)
    >>> arr_float = numpy.array([1, 2, 3, 4], dtype = float64)
    >>> my_function(arr_int)  # No type errors
    >>> my_function(arr_float)  # Raises AssertionError
    Traceback (most recent call last):
        ...
    AssertionError: a is not an instance of <class 'numpy.int32'>

    When applied to a function inside a class, use the parameter classmethod=True

    >>> class  MyClass:
    ...
    >>>     @classmethod
    >>>     @type_check(classmethod=True)
    >>>     def my_func():
    ...         pass



    """

    def decorator(func: typing.Callable[..., T]) -> typing.Callable[..., T]:
        var_name_and_type = typing.get_type_hints(func)
        var_names = list(var_name_and_type.keys())

        if classmethod:
            # adding an empty element to account for cls argument
            var_names = [""] + var_names

        @wraps(func)
        def wrapper(*args, **kwargs):
            for i, arg in enumerate(args):
                if classmethod and i == 0:
                    # skipping first element for classmethods
                    pass
                else:
                    arg_type = var_name_and_type[var_names[i]]
                    _check_arg(arg, arg_type)

            for kwarg_name, kwarg in kwargs.items():
                kwarg_type = var_name_and_type[kwarg_name]
                _check_arg(kwarg, kwarg_type)

            return func(*args, **kwargs)

        return wrapper

    return decorator
