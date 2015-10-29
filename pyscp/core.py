#!/usr/bin/env python3

"""
Abstract Base Classes.

pyscp builds most of its functionality on top of three large classes: Wiki,
Page, and Thread. This module contains the abstract base classes for those
three. The ABC-s define the abstact methods that each child must implement,
as well as some common functionality that builds on top of the abstract
methods.

Each class inheriting from the ABC-s must implement its own realization of
the abstract methods, and can also provide additional methods unique to it.

This module also defines the named tuples for simple containers used by the
three core classes, such as Revision or Vote.
"""


###############################################################################
# Module Imports
###############################################################################

import abc
import bs4
import collections
import functools
import itertools
import logging
import re
import urllib.parse

import pyscp.utils

###############################################################################
# Global Constants And Variables
###############################################################################

log = logging.getLogger(__name__)

###############################################################################
# Abstract Base Classes
###############################################################################


class Page(metaclass=abc.ABCMeta):

    """
    Page Abstract Base Class.

    Page object are wrappers around individual wiki-pages, and allow simple
    operations with them, such as retrieving the rating or the author.

    Each Page instance is attached to a specific instance of the Wiki class.
    The wiki may be used by the page to retrieve a list of titles or other
    similar wiki-wide information that may be used by the Page to, in turn,
    deduce some information about itself.

    Typically, the Page instances should not be created directly. Instead,
    calling an instance of a Wiki class will creating a Page instance
    attached to that wiki.
    """

    ###########################################################################
    # Special Methods
    ###########################################################################

    def __init__(self, wiki, url):
        if wiki.site not in url:
            url = '{}/{}'.format(wiki.site, url)
        url = url.replace(' ', '-').replace('_', '-')
        self.url = url.lower()
        self._wiki = wiki

    def __repr__(self):
        return '{}.{}({}, {})'.format(
            self.__module__, self.__class__.__name__,
            repr(self.url), repr(self._wiki))

    ###########################################################################
    # Abstract Methods
    ###########################################################################

    @property
    @abc.abstractmethod
    def _pdata(self):
        """
        Commonly used data about the page.

        This method should return a tuple, the first three elements of which
        are the id number of the page; the id number of the page's comments
        thread; and the html contents of the page.

        Any additional elements of the tuple are left to the discretion
        of the individual Page implimentations.
        """
        pass

    @property
    @abc.abstractmethod
    def history(self):
        """
        Revision history of the page.

        Should return a sorted list of Revision named tuples.
        """
        pass

    @property
    @abc.abstractmethod
    def votes(self):
        """
        Page votes.

        Should return a list of Vote named tuples.
        """
        pass

    @property
    @abc.abstractmethod
    def tags(self):
        """
        Page tags.

        Should return a set of strings.
        """
        pass

    ###########################################################################
    # Internal Methods
    ###########################################################################

    @property
    def _id(self):
        """Unique ID number of the page."""
        return self._pdata[0]

    @pyscp.utils.cached_property
    def _thread(self):
        """Thread object corresponding to the page's comments thread."""
        return self._wiki.Thread(self._wiki, self._pdata[1])

    @property
    def _title(self):
        """Title as displayed on the page."""
        title = self._soup.find(id='page-title')
        return title.text.strip() if title else ''

    @property
    def _soup(self):
        """BeautifulSoup of the contents of the page."""
        return bs4.BeautifulSoup(self.html, 'lxml')

    ###########################################################################
    # Properties
    ###########################################################################

    @property
    def html(self):
        """HTML contents of the page."""
        return self._pdata[2]

    @property
    def posts(self):
        """List of the comments made on the page."""
        return self._thread.posts

    @property
    def comments(self):
        """Alias for Page.posts."""
        return self._thread.posts

    @property
    def text(self):
        """Plain text of the page."""
        return self._soup.find(id='page-content').text

    @property
    def wordcount(self):
        """Number of words encountered on the page."""
        return len(re.findall(r"[\w'█_-]+", self.text))

    @property
    def images(self):
        """Number of images dislayed on the page."""
        # TODO: needs more work.
        return [i['src'] for i in self._soup('img')]

    @property
    def title(self):
        """
        Title of the page.

        In case of SCP articles, will include the title from the 'series' page.
        """
        if 'scp' in self.tags and re.search('[scp]+-[0-9]+$', self.url):
            try:
                return '{}: {}'.format(
                    self._title, self._wiki.titles()[self.url])
            except KeyError:
                pass
        return self._title

    @property
    def created(self):
        """When was the page created."""
        return self.history[0].time

    @property
    def author(self):
        """Original author of the page."""
        for over in self._wiki.list_overrides():
            if over.url == self.url and over.type == 'author':
                return over.user if over.user != 'Unknown Author' else None
        author = self.history[0].user
        if any(map(author.startswith, ['Anonymous', '(accound deleted)'])):
            return None
        return author

    @property
    def rewrite_author(self):
        """Author of the current rewrite."""
        for over in self._wiki.list_overrides():
            if over.url == self.url and over.type == 'rewrite_author':
                return over.user

    @property
    def rating(self):
        """Rating of the page, excluding deleted accounts."""
        return sum(
            v.value for v in self.votes if v.user != '(account deleted)')

    @property
    @pyscp.utils.listify()
    def links(self):
        """
        Other pages linked from this one.

        Returns an ordered list of unique urls. Off-site links or links to
        images are not included.
        """
        unique = set()
        for element in self._soup.select('#page-content a'):
            href = element.get('href', None)
            if (not href or href[0] != '/' or  # bad or absolute link
                    href[-4:] in ('.png', '.jpg', '.gif')):
                continue
            url = self._wiki.site + href.rstrip('|')
            if url not in unique:
                unique.add(url)
                yield url


class Thread(metaclass=abc.ABCMeta):

    """
    Thread Abstract Base Class.

    Thread objects represent individual forum threads. Most pages have a
    corresponding comments thread, accessible via Page._thread.
    """

    def __init__(self, wiki, _id, title=None, description=None):
        self._wiki = wiki
        self._id, self.title, self.description = _id, title, description

    @abc.abstractmethod
    def posts(self):
        """Posts in this thread."""
        pass


class Wiki(metaclass=abc.ABCMeta):
    """
    Wiki Abstract Base Class.

    Wiki objects provide wiki-wide functionality not limited to individual
    pages or threads.
    """

    ###########################################################################
    # Class Attributes
    ###########################################################################

    # should point to the respective Page and Thread classes in each submodule.

    Page = Page
    Thread = Thread

    ###########################################################################
    # Special Methods
    ###########################################################################

    def __init__(self, site):
        parsed = urllib.parse.urlparse(site)
        netloc = parsed.netloc if parsed.netloc else parsed.path
        if '.' not in netloc:
            netloc += '.wikidot.com'
        self.site = urllib.parse.urlunparse(['http', netloc, '', '', '', ''])

    def __call__(self, url):
        return self.Page(self, url)

    ###########################################################################

    @functools.lru_cache(maxsize=1)
    def titles(self):
        """Dict of url/title pairs for scp articles."""
        pages = map(self, ('scp-series', 'scp-series-2', 'scp-series-3'))
        elems = [p._soup.select('ul > li') for p in pages]
        elems = itertools.chain(*elems)
        titles = {}
        splash = set(self.list_pages(tag='splash'))
        for elem in elems:
            if not re.search('[SCP]+-[0-9]+', elem.text):
                continue
            url = self.site + elem.a['href']
            try:
                skip, title = elem.text.split(' - ', maxsplit=1)
            except ValueError:
                skip, title = elem.text.split(', ', maxsplit=1)
            if url in splash:
                url = '{}/{}'.format(self.site, skip.lower())
            titles[url] = title
        return titles

    def list_pages(self, **kwargs):
        """
        Return pages matching the specified criteria.
        """
        urls = self._urls(**kwargs)
        author = kwargs.pop('author', None)
        if not author:
            # if 'author' isn't specified, there's no need to check rewrites
            yield from map(self, urls)
            return
        include, exclude = set(), set()
        for over in self.list_overrides():
            if over.user == author:
                # if username matches, include regardless of type
                include.add(over.url)
            elif over.type == 'author':
                # exclude only if override type is author.
                # if url has author and rewrite author,
                # it will appear in list_pages for both.
                exclude.add(over.url)
        urls = set(urls) | include - exclude
        # if no other options beside author were specified,
        # just return everything we can
        if not kwargs:
            yield from map(self, sorted(urls))
            return
        # otherwise, retrieve the list of urls without the author parameter
        # to check which urls we should return and in which order
        for url in self._urls(**kwargs):
            if url in urls:
                yield self(url)

###############################################################################
# Named Tuple Containers
###############################################################################

nt = collections.namedtuple
Revision = nt('Revision', 'id number user time comment')
Vote = nt('Vote', 'user value')
Post = nt('Post', 'id title content user time parent')
Override = nt('Override', 'url user type')
Category = nt('Category', 'id title description size')
Image = nt('Image', 'url source status notes data')
del nt
