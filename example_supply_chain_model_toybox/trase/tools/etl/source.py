import inspect


class GetSource(type):
    """Fetches the source code of the class on instantiation.

    Once a Python class has been instantiated, it can be difficult to reconstruct the
    source code. ``inspect.getsource`` will locate the original file and load the text
    from there, but that assumes that the file hasn't changed between instantiating the
    class and calling the function. Third-party libraries like ``dill`` are cleverer,
    but still don't handle re-loaded code very well. Python gives you the ability to
    access the byte code, but this carries less informational content than the source
    code.

    This metaclass fetches the source code immediately after the class was instantiated.
    Use it as follows:

    ```python
    # my_module.py

    class MyClass(metaclass=GetSource):
        pass
    ```

    Then you can access the source code like this:

    ```python
    import my_module
    my_module.MyClass._source
    ```

    Crucially, the source code will also be updated should you reload the module
    using ``importlib.reload``. We do not attempt to capture interactive code (i.e. in
    module __main__): in this case the source code will be ``None``.
    """

    def __init__(cls, *args, **kwargs):
        cls._source = inspect.getsource(cls) if cls.__module__ != "__main__" else None
        super().__init__(*args, **kwargs)
