import collections
import datetime

from .parser import DateLine, EntryLine, TextLine, TimesheetParser


def synchronized(func):
    """
    Only run the function body if the synchronized flag of the current object
    is set.
    """
    def wrapper(*args):
        if args[0].synchronized:
            return func(*args)

    return wrapper


class EntriesCollection(collections.defaultdict):
    """
    An entries collection is a subclass of defaultdict, with dates as keys and
    lists of entries (as EntriesList) as items. This collection keeps its
    structured data synchronized with a list of text lines, allowing to easily
    export it to a text format, without altering the original data.

    Use this class as you would use a standard defaultdict, it will take care
    of automatically synchronizing the textual representation with the
    structured data.
    """
    def __init__(self, entries=None):
        super(EntriesCollection, self).__init__(EntriesList)

        self.lines = []
        # This flag allows to enable/disable synchronization with the internal
        # text representation, useful when building the initial structure from
        # the text representation
        self.synchronized = True
        # Whether to add new dates at the start or at the end in the textual
        # representation
        self.add_date_to_bottom = False

        # If there are initial entries to import, disable synchronization and
        # import them in the structure
        if entries:
            self.synchronized = False

            try:
                self.init_from_str(entries)
            finally:
                self.synchronized = True

    def __missing__(self, key):
        """
        Automatically called when the given date (key) doesn't exist. In that
        case, create the EntriesList for that key, attach it the entries
        collection (to allow callbacks when an item is added/removed) and the
        date. Also if we're in synchronized mode, add the date line to the
        textual representation.
        """
        self[key] = self.default_factory(self, key)

        if self.synchronized:
            self.add_date(key)

        return self[key]

    def __delitem__(self, key):
        """
        If in synchronized mode, delete the date and its entries from the
        textual representation.
        """
        if self.synchronized:
            self.delete_entries(self[key])
            self.delete_date(key)

        super(EntriesCollection, self).__delitem__(key)

    @synchronized
    def add_entry(self, date, entry):
        """
        Add the given entry to the textual representation.
        """
        in_date = False
        insert_at = None

        for (lineno, line) in enumerate(self.lines):
            # Search for the date of the entry
            if isinstance(line, DateLine) and line.date == date:
                in_date = True
                # Insert here if there is no existing EntryLine for this date
                insert_at = lineno
                continue

            if in_date:
                if isinstance(line, EntryLine):
                    insert_at = lineno
                elif isinstance(line, DateLine):
                    break

        new_line = EntryLine(entry.alias, entry.duration, entry.description)
        entry.line = new_line

        self.lines.insert(insert_at + 1, new_line)

        # If there's no other EntryLine in the current date, add a blank line
        # between the date and the entry
        if not isinstance(self.lines[insert_at], EntryLine):
            self.lines.insert(insert_at + 1, TextLine(''))

    def delete_entry(self, entry):
        """
        Remove the given entry from the textual representation.
        """
        self.delete_entries([entry])

    @synchronized
    def delete_entries(self, entries):
        """
        Remove the given entries from the textual representation.
        """
        lines_to_delete = [entry.line for entry in entries]

        self.lines = [
            line for line in self.lines
            if not isinstance(line, EntryLine) or line not in lines_to_delete
        ]

        # Remove trailing whitelines
        self.trim()

    @synchronized
    def delete_date(self, date):
        """
        Remove the date line from the textual representation. This doesn't
        remove any entry line.
        """
        self.lines = [
            line for line in self.lines
            if not isinstance(line, DateLine) or line.date != date
        ]

        self.trim()

    def trim(self):
        """
        Remove blank lines at the beginning and at the end of the textual
        representation.
        """
        trim_top = None
        trim_bottom = None

        for (lineno, line) in enumerate(self.lines):
            if isinstance(line, TextLine) and not line.text.strip():
                trim_top = lineno
            else:
                break

        for (lineno, line) in enumerate(reversed(self.lines)):
            if isinstance(line, TextLine) and not line.text.strip():
                trim_bottom = lineno
            else:
                break

        if trim_top is not None:
            self.lines = self.lines[trim_top + 1:]

        if trim_bottom is not None:
            trim_bottom = len(self.lines) - trim_bottom - 1
            self.lines = self.lines[:trim_bottom]

    @synchronized
    def add_date(self, date):
        """
        Add the given date to the textual representation.
        """
        if self.add_date_to_bottom:
            self.lines.append(DateLine(date))
        else:
            self.lines.insert(0, TextLine(''))
            self.lines.insert(0, DateLine(date))

    def init_from_str(self, entries):
        """
        Initialize the structured and textual data based on a string
        representing the entries. For detailed information about the format of
        this string, refer to the TimesheetParser class.
        """
        self.lines = TimesheetParser.parse(entries)

        for line in self.lines:
            if isinstance(line, DateLine):
                current_date = line.date
            elif isinstance(line, EntryLine):
                timesheet_entry = TimesheetEntry(
                    line.alias, line.duration, line.description
                )
                timesheet_entry.line = line
                self[current_date].append(timesheet_entry)


class EntriesList(list):
    """
    The EntriesList class is a classic list that synchronizes its data with the
    textual representation from the bound entries collection.
    """
    def __init__(self, entries_collection, date):
        super(EntriesList, self).__init__()

        self.entries_collection = entries_collection
        self.date = date

    def append(self, x):
        """
        Append the given element to the list and synchronize the textual
        representation.
        """
        super(EntriesList, self).append(x)

        if (len(self) > 1 and isinstance(x.duration, tuple) and
                isinstance(self[-2].duration, tuple) and x.duration[0] is None):
            x.duration = (self[-2].duration[1], x.duration[1])

        if self.entries_collection is not None:
            self.entries_collection.add_entry(self.date, x)

    def __delitem__(self, key):
        """
        Delete the given element from the list and synchronize the textual
        representation.
        """
        if self.entries_collection is not None:
            self.entries_collection.delete_entry(self[key])

        super(EntriesList, self).__delitem__(key)

        if not self and self.entries_collection is not None:
            self.entries_collection.delete_date(self.date)


class TimesheetEntry(object):
    def __init__(self, alias, duration, description):
        self.line = None
        self.ignored = False
        self.commented = False

        self.alias = alias
        self.description = description
        self.duration = duration

    def __unicode__(self):
        if self.is_ignored():
            project_name = u'%s (ignored)' % self.alias
        else:
            project_name = self.alias

        return u'%-30s %-5.2f %s' % (project_name, self.hours,
                                     self.description)

    def __setattr__(self, name, value):
        """
        Apply attribute modifications to the bound line if necessary.
        """
        super(TimesheetEntry, self).__setattr__(name, value)

        if self.line is not None:
            if hasattr(self.line, name):
                setattr(self.line, name, value)

    @property
    def hash(self):
        return u'%s%s%s' % (
            self.activity,
            self.description,
            self.ignored
        )

    def is_ignored(self):
        return self.ignored or self.hours == 0

    @property
    def hours(self):
        if isinstance(self.duration, tuple):
            if None in self.duration:
                return 0

            now = datetime.datetime.now()
            time_start = now.replace(
                hour=self.duration[0].hour,
                minute=self.duration[0].minute, second=0
            )
            time_end = now.replace(
                hour=self.duration[1].hour,
                minute=self.duration[1].minute, second=0
            )
            total_time = time_end - time_start
            total_hours = total_time.seconds / 3600.0

            return total_hours

        return self.duration
