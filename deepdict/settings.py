# -*- coding: utf-8 -*-

# Standard Python modules
# =======================
from collections import OrderedDict
import os
from reprlib import recursive_repr

# External modules
# ================

# DICE modules
# ============
from dice.dice_extras.tools.json_sync import JsonOrderedDict


class Settings(dict):
    """
    Manages various configuration parameters and stores it.
    Could be used as dict or object.

    Example:
    Let`s

    s = Settings()

    then

    s["foo"] = {"bar": "val"}

    or

    s["foo"]["bar"] = "val"

    or

    s["foo.bar"] = "val"

    or

    s.foo.bar = "val"

    are equivalents.

    So

    c1 = s.foo

    c2 = s["foo"]

    c1 == c2 == {"bar": "val"}

    c1 = s["foo"]["bar"]

    c2 = s["foo.bar"]

    c3 = s.foo.bar

    c1 == c2 == c3 == "val"
    """

    def __init__(self, file_name=None, autowrite=True, use_qt_watcher=False,
                 file_necessary=True, on_change=None, class_type=None,
                 readonly=False, **kwargs):
        """
        :param file_name: Name of file where parameters writen. By default =
         os.path.join(os.path.expanduser("~"), ".config", "DICE", "dice.json").
         If file_necessary=False and class_type is not None, object of
         class_type responsible for file operations.
        :param autowrite: Automatically write to file with file_name on every change.
        :param use_qt_watcher: Use QFileSystemWatcher instead of watchdog.
        :param file_necessary: If True, give file_name it`s default value.
        :param on_change: Callback function to call on external file changes.
        :param class_type: Type of object used for internal storage. Defaults to JsonOrderedDict.
        :param readonly: Sets could we change items values
        :param kwargs: Parameters for class_type object, if any.
        """
        super(Settings, self).__init__()
        self.file_name = os.path.abspath(file_name) if file_name else file_name
        self.autowrite = autowrite
        self.__on_change = on_change
        self.__is_watcher_on = False
        if self.file_name is None and file_necessary:
            self.file_name = os.path.join(
                    os.path.expanduser("~"), ".config", "DICE", "dice.json")

        if file_necessary or file_name:
            if use_qt_watcher:
                self.__init_qt_watcher()
            else:
                try:
                    self.__init_watchdog()
                except ImportError:
                    # Fall back to QFileSystemWatcher
                    self.__init_qt_watcher()

        if class_type is None:
            storage = JsonOrderedDict(self.file_name, self.autowrite)
        elif self.file_name is None:
            storage = class_type(**kwargs)
        else:
            args = kwargs
            args['file_name'] = self.file_name
            args['autowrite'] = self.autowrite
            storage = class_type(**args)
        self.__dict__["_Settings__storage"] = self.Storage(
            storage, readonly=readonly)

    def write(self):
        self.__storage.write()

    def items(self):
        return self.__storage.items()

    def __init_watchdog(self):
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, \
            FileModifiedEvent

        # Define handler class for the watchdog`s Observer
        self.handler = type('Handler', (FileSystemEventHandler,),
                            {'callback': self.__update_storage,
                             'file_name': self.file_name})
        self.handler.on_created = lambda obj, event: obj.callback()
        self.handler.on_modified = lambda obj, event: obj.callback() \
            if isinstance(event, FileModifiedEvent) \
               and event.src_path == obj.file_name else ''
        self.handler.on_moved = lambda obj, event: \
            exec('raise FileNotFoundError') \
                if event.src_path == obj.file_name else ''
        self.handler.on_deleted = lambda obj, event: \
            exec('raise FileNotFoundError') \
                if event.src_path == obj.file_name else ''

        self.observer = Observer()
        path = os.path.dirname(self.file_name)
        self.observer.schedule(self.handler(), path)
        self.observer.start()
        self.__is_watcher_on = True

    def __init_qt_watcher(self):
        from PyQt5.QtCore import QFileSystemWatcher
        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(self.__update_storage)
        self.__watcher_on()
        self.is_watcher_set = self.watcher.addPath(self.file_name)

    def __update_storage(self):
        if not self.__is_watcher_on:
            return
        self.__watcher_off()
        self.__storage.read()
        if self.__on_change is not None:
            self.__on_change()
        from threading import Timer
        Timer(1, self.__watcher_on).start()

    def __watcher_on(self):
        self.__dict__["_Settings__is_watcher_on"] = True

    def __watcher_off(self):
        self.__dict__["_Settings__is_watcher_on"] = False

    def __getitem__(self, item):
        def helper(key, array):
            # If key contains ".", take key part after "." and do the same
            if "." in key:
                return helper('.'.join(key.split(".")[1:]),
                              array[key.split(".")[0]])
            else:
                return array[key]

        self.__watcher_off()
        ret = helper(item, self.__storage)
        self.__watcher_on()
        return ret

    def __getattr__(self, item):
        # If item is attribute of this class, return it
        if item in self.__dict__:
            return self.__dict__[item]
        else:
            self.__watcher_off()
            ret = self.__storage[item]
            self.__watcher_on()
            return ret

    def __setitem__(self, key, value):
        def helper(d, item, val):
            """
            Constructs [nested] dict.
            :param d: The dict
            :param item: Dict key. If contains ".", nested dict will be created
            :param val: Value for deepest level of dict
            :return: dict
            """
            ret = d if d else OrderedDict()
            if "." in item:
                ret[item.split(".")[0]] = helper(
                    ret[item.split(".")[0]], '.'.join(item.split(".")[1:]), val)
            else:
                ret[item] = val
            return ret

        self.__watcher_off()
        if "." in key:
            self.__storage[key.split(".")[0]] = helper(
                self.__storage[key.split(".")[0]],
                '.'.join(key.split(".")[1:]), value)
        else:
            self.__storage[key] = value

        self.__watcher_on()

        if "watcher" in self.__dict__:
            # Initially settings file may not be present. So try once again.
            if not self.is_watcher_set:
                self.watcher.addPath(self.file_name)

    def __delitem__(self, key):
        if key in self.__dict__:
            return
        if key in self.__storage:
            self.__watcher_off()
            del self.__storage[key]
            self.__watcher_on()

    def __setattr__(self, key, value):
        # If key is attribute of this class, set it to value
        if key in self.__dict__:
            self.__dict__[key] = value
        elif "_Settings__storage" in self.__dict__:
            self.__watcher_off()
            self.__storage[key] = value
            self.__watcher_on()
        else:  # Hook for __init__()
            self.__dict__[key] = value
            return

    def __iter__(self):
        return iter(self.__storage)

    def keys(self):
        return self.__storage.keys()

    def __contains__(self, item):
        def helper(d, key):
            d = d if d else OrderedDict()
            if '.' in key:
                i = key.split('.')[0]
                if i in d:
                    return helper(d[i], '.'.join(key.split('.')[1:]))
                else:
                    return False
            else:
                return key in d

        if '.' in item:
            itm = item.split('.')[0]
            if itm in self.__storage:
                return helper(self.__storage[itm],
                              '.'.join(item.split('.')[1:]))
            else:
                return False
        else:
            return item in self.__storage

    def __len__(self):
        return len(self.__storage)

    def __eq__(self, other):
        return self.__storage == other

    @recursive_repr()
    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__,
                           self.__storage.__repr__())

    class Storage(dict):
        def __init__(self, storage=None, parent=None, parent_name="",
                     readonly=False):
            super(Settings.Storage, self).__init__()
            if storage is not None:
                self.__storage = storage
            else:
                self.__storage = OrderedDict()
            self.__parent = parent
            self.__parent_name = parent_name
            self.__readonly = readonly

        def read(self):
            if hasattr(self.__storage, "read"):
                self.__storage.read()

        def write(self):
            if hasattr(self.__storage, "write"):
                self.__storage.write()

        def items(self):
            return self.__storage.items()

        def keys(self):
            return self.__storage.keys()

        def __get_parent(self):
            if "_Storage__parent" in self.__dict__ \
                    and self.__dict__["_Storage__parent"] is not None \
                    and "_Storage__parent_name" in self.__dict__ \
                    and self.__dict__["_Storage__parent_name"]:
                return self.__dict__["_Storage__parent"]
            else:
                return None

        def __set_parent_value(self, value):
            if "_Storage__parent" in self.__dict__ \
                    and self.__dict__["_Storage__parent"] is not None:
                self.__dict__["_Storage__parent"][
                    self.__dict__["_Storage__parent_name"]] = value

        def __getitem__(self, item):
            return self.__getattr__(item)

        def __getattr__(self, item):
            ret = None
            if "_Storage__storage" not in self.__dict__:
                return ret
            if item in self.__dict__["_Storage__storage"]:
                ret = self.__dict__["_Storage__storage"][item]
            if ret is None:
                ret = Settings.Storage(
                        parent=self.__dict__["_Storage__storage"],
                        parent_name=item)
                self.__dict__["_Storage__storage"][item] = ret
            if type(ret) == OrderedDict or type(ret) == dict:
                ret1 = Settings.Storage(
                        parent=self.__dict__["_Storage__storage"],
                        parent_name=item)
                autowrite = None
                if hasattr(self.__dict__["_Storage__storage"], "autowrite"):
                    autowrite = self.__dict__["_Storage__storage"].autowrite
                    self.__dict__["_Storage__storage"].autowrite = False
                for key in ret:
                    ret1[key] = ret[key]
                if autowrite:
                    self.__dict__["_Storage__storage"].autowrite = autowrite
                ret = ret1
            return ret

        def __setattr__(self, key, value):
            if key in ("_Storage__storage", "_Storage__parent",
                       "_Storage__parent_name", "_Storage__readonly") or \
                            key in self.__dict__:
                self.__dict__[key] = value
            else:
                if self.__readonly and \
                                key in self.__dict__["_Storage__storage"]:
                    raise KeyError("The storage is read only")
                self.__dict__["_Storage__storage"][key] = value
                parent = self.__get_parent()
                if parent is not None:
                    self.__set_parent_value(
                            self.__dict__["_Storage__storage"])

        def __setitem__(self, key, value):
            self.__setattr__(key, value)

        def __delitem__(self, key):
            if key in self.__dict__:
                return
            if key in self.__dict__["_Storage__storage"]:
                del self.__dict__["_Storage__storage"][key]

        def __iter__(self):
            return iter(self.__storage)

        def __contains__(self, item):
            return item in self.__storage

        def __len__(self):
            return len(self.__storage)

        def __eq__(self, other):
            return self.__storage == other

        @recursive_repr()
        def __repr__(self):
            return '%r' % list(self.__storage.items())
