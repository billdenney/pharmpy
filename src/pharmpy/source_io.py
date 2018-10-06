# -*- encoding: utf-8 -*-
"""
=============================
Generic Sources/Resources I/O
=============================

Source code/resource manager for a :class:`~pharmpy.generic.Model` class implementation.

Cached input
------------

The input is cached as much as possible, with automatic invalidation. Yes that's right. *Cached*.
Why? Because :attr:`SourceResource.input` must be trusted to be **the exact input** that was/is used
for all the other API's. If not, it's *useless*.

The desire for some great input immutability is what motivated this module.

Noteworthy
----------

Module is target for *all* generalizable and non-agnostic code that concerns:

    1. Reading *in* streams/file-like resources.
    2. Formatting/generating source code from current state of :class:`~pharmpy.generic.Model`.
    3. Writing *out* source code to streams/file-like resources.
    4. Detecting changes and managing concurrency/version control of such I/O resources.

Path changes
------------

:attr:`SourceResource.path` *getter* returns resolved path of this source, or ``None`` if none.

*Setter* will signal other API:s (see table below) of the move, to give them a chance to update
their internal (relative) filesystem dependencies. A guiding map, relative path of new dir -> old
dir, is supplied in the call. If such an update fails (e.g. change of filesystem), it is *strongly
recommended* to convert all relative paths into absolute paths!

.. list-table::
    :widths: 20 80
    :stub-columns: 1

    - - :func:`ModelInput.repath <pharmpy.input.ModelInput.repath>`
      - Updates :attr:`ModelInput.path <pharmpy.input.ModelInput.path>`, the "dataset" path.

Definitions
-----------
"""

from io import StringIO
from os.path import realpath
from os.path import relpath
from pathlib import Path


class SourceIO(StringIO):
    """An IO class for reading/writing :class:`~pharmpy.generic.Model` source code.

    Arguments:
        file: Path of the file containing the initializing source.
        source: The source code if no *file*.
    """

    def __init__(self, file=None, source=''):
        if file:
            with open(str(file), 'r') as source_file:
                source = source_file.read()
        super().__init__(source)

    def __str__(self):
        return str(self.getvalue())


class SourceResource:
    """A manager of (source code) resource input/output of a :class:`~pharmpy.generic.Model`.

    Is a model API attached to attribute :attr:`Model.source <pharmpy.generic.Model.source>`.

    .. note:: Implementation should only need to override :func:`generate_source`
    """

    model = None
    """:class:`~pharmpy.generic.Model` owner of API."""

    SourceIO = SourceIO
    """:class:`~pharmpy.source_io.SourceIO` implementation."""

    def __init__(self, path):
        if path:
            self._path = Path(path)
        else:
            self._path = None
        self._cache = dict()

    @property
    def input(self):
        """Input source code."""
        if self.on_disk:
            if 'input' not in self._cache:
                self._cache['input'] = self.SourceIO(file=self.path)
            return self._cache['input']
        else:
            return self.SourceIO(source='')

    @property
    def output(self):
        """Output source code."""
        return self.SourceIO(source=self.source_generator(self.model))

    @property
    def path(self):
        """Source on disk as a (resolved) `path-like object`_ (or None).

        .. _path-like object: https://docs.python.org/3/glossary.html#term-path-like-object"""
        if not self._path:
            return None
        try:
            return self._path.resolve()
        except FileNotFoundError:
            return Path(realpath(str(self._path)))

    @path.setter
    def path(self, path):
        path = Path(path)
        assert not path.exists() or path.is_file(), ('source path change, but non-file exists at '
                                                     'target (%s)' % str(path))
        if path:
            try:
                new_to_old = relpath(str(self._path.parent), str(path.parent))
            except ValueError:
                new_to_old = None
            path = Path(path)
        else:
            path = None
            new_to_old = None
        self.model.input.repath(new_to_old)
        self._path = path
        self._cache = dict()

    @property
    def on_disk(self):
        """Returns True if readable."""
        return self.path and self.path.exists() and self.path.is_file()

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.path)

    @classmethod
    def source_generator(cls, model):
        """Generator of source code.

        Generated source must be:

            1. Current, i.e. :class:`~pharmpy.generic.Model` state-dependent (limit side-effects).
            2. *Fully* agnostic of existing files and other resources. Again, no side-effects!
        """
        return str(model)