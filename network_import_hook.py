"""
PEP302 give a lot of inforation about the working of this module
https://www.python.org/dev/peps/pep-0302/
"""
import imp
import logging
import sys

import requests

# Define the order to search for an import.
# First we look for a package __init__ then for non-package .py files.
# We do not look for non-pure Python files, the remote machine may have
# a different Python version / architecture / anything.
_SEARCH_ORDER = ["/__init__.py", ".py"]


class NetworkImportHook(object):
    log = logging.getLogger('NetworkImportHook')

    def __eq__(self, other):
        return (self.__class__.__module__ == other.__class__.__module__ and
                self.__class__.__name__ == other.__class__.__name__)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "<NetworkImportHook>"

    def install(self):
        """
        Add the import hook to sys.meta_path, if it's not already there
        """
        self.log.debug("Installing %r", self)
        sys.meta_path[:] = [x for x in sys.meta_path if self != x] + [self]

    def find_module(self, fullname, path=None):
        """
        Part of the import hook's finder.
        Should find out if fullname exists as a package or module, possibly
        by searching for fullname/__init__.py or fullname.py. If one exists,
        self should be returned, otherwise None.

        "It should return a loader object if the module was found, or None
        if it wasn't. If find_module() raises an exception, it will be
        propagated to the caller, aborting the import."
        See PEP302
        """
        raise NotImplementedError("Implement in subclass")

    def _create_module(self, fullname, filename, content):
        """
        Given some python source and filename info, return a module
        """
        try:
            mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
            mod.__file__ = "<%s>" % filename
            mod.__loader__ = self
            if (mod.__file__.endswith('__init__.py>') and
                    not fullname.endswith('__init__.py')):
                # We imported a package
                mod.__path__ = []
                mod.__package__ = fullname
            else:
                mod.__package__ = fullname.rsplit('.', 1)[0]
        except Exception as e:
            del sys.modules[fullname]
            raise ImportError("%r was unable to create module '%s': [%s]"
                              % (self, fullname, e))

        self.log.debug("Imported '%s'", fullname)

        exec(content, mod.__dict__)
        return mod

    def load_modules(self, fullname):
        """
        Given a fullname should do what is necessary (load, unpackage,
        evaluate, etc.) to construct a module object.

        Pretty much, just get the Python source and pass it to _create_module.
        """
        raise NotImplementedError("Implement in subclass")


class HttpChannel(NetworkImportHook):
    log = logging.getLogger('HttpChannel')

    def __init__(self, host):
        self.host = host
        self.session = requests.Session()
        try:
            # Run a request to trigger request's imports.
            # We don't care if it works
            requests.options(self.host)
        except:
            pass

    def __repr__(self):
        return "<HttpChannel(%r)>" % (self.host,)

    def get_filename(self, fullname, so):
        return self.host + "/" + fullname.replace('.', '/') + so

    def find_module(self, fullname, path=None):
        """
        Search for package or module from fullname.

        If one is found, return's self, otherwise None.
        """
        for so in _SEARCH_ORDER:
            try:
                path = self.get_filename(fullname, so)
                self.request = self.session.get(path)
                self.request.raise_for_status()
                return self
            except requests.exceptions.RequestException as e:
                self.log.debug("Unable to import %s: [%s]", path, e)

    def load_module(self, fullname):
        """
        Returns the loaded module or raises an exception
        """
        if fullname in sys.modules:
            return sys.modules[fullname]

        return self._create_module(fullname, self.request.url,
                                   self.request.content)
