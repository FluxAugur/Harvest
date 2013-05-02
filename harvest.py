import base64 
import datetime
import decimal
import functools
import string
import types
from urllib import urlencode
import urllib2
from xml.etree import ElementTree

<<<<<<< HEAD
'''
import urllib2
from base64 import b64encode
from dateutil.parser import parse as parseDate
from xml.dom.minidom import parseString
=======
from dateutil import parser as date_parser
>>>>>>> origin/new_version

USER_AGENT = 'harvest.py'

class Harvest(object):
    def __init__(self, url, email, password):
        self.base_url = url
        self.headers = {
            'Authorization': 'Basic %s' % (
                base64.b64encode('%s:%s' % (email, password))),
            'Accept': 'application/xml',
            'Content-Type': 'application/xml',
            'User-Agent': USER_AGENT,
            }

    def _request(self, url, data=None, method=None):
        request = HTTPRequest(
            url=self.base_url + url,
            headers=self.headers,
            data=data,
            method=method,
            )

        try:
            response = urllib2.urlopen(request)
        except urllib2.URLError, e:
            print e, url
            raise HarvestConnectionError(*e.args)

        try:
            return ElementTree.parse(response)
        except ElementTree.ParseError, e:
            raise HarvestError('Parse Error', *e.args)
    
    def _get_item(self, cls, url):
        try:
            return self._get_items(cls, url).next()
        except StopIteration:
            return None
        
    def _get_items(self, cls, url):
        root = self._request(url)
        for element in root.findall('.//%s' % cls.element_name):
            yield self._item_from_element(cls, element)

    def _item_from_element(self, cls, element):
        def to_python(typ_name, val):
            try:
                typ = dict(
                    str=str,
                    integer=int,
                    float=float,
                    decimal=decimal.Decimal,
                    datetime=date_parser.parse,
                    date=lambda v: date_parser.parse(v).date(),
                    boolean=bool,
                    )[typ_name]
                try:
                    return typ(val)
                except ValueError, e:
                    return typ()
            except:
                return val
            
        data = {}
        for prop in element.getchildren():
            data[prop.tag.replace('-', '_')] = to_python(
                prop.attrib.get('type'), prop.text)
        return cls(self, data)
        
class HarvestError(Exception):
    pass

class HarvestConnectionError(HarvestError):
    pass

        
def _build_url(base_url, *parts, **params):
    url = '/'.join([base_url] + map(str, parts))
    
    if params:
        def to_str(obj):
            if isinstance(obj, datetime.datetime):
                return obj.strftime('%Y-%m-%d %H:%M')
            elif isinstance(obj, datetime.date):
                return obj.strftime('%Y%m%d')
            elif isinstance(obj, bool):
                return obj and 'yes' or 'no'
            else:
                return str(obj)
        params = dict((k, to_str(v)) for k, v in params.items())
        
        url = '%s?%s' % (url, urlencode(params))
        
    return url

        
# Harvest item base classes and magic

class HarvestItemBase(object):
    def __init__(self, harvest, data):
        self.__dict__.update(data)
        self.harvest = harvest

    def __str__(self):
        return '%s: %s' % (self.__class__.__name__,
                           getattr(self, 'name', None) or 
                           getattr(self, 'id', '<no id>'))

def _cls_to_element(name):
    return ''.join(
        [name[0].lower()] 
        + map(lambda l: '-' + l if l in string.uppercase else l, name[1:]))
    
class _GettableType(type):
    def __init__(cls, name, bases, attrs):
        super(_GettableType, cls).__init__(name, bases, attrs)
        
        if not cls.__dict__.get('_abstract'):
        
            # Resolve Item names
            cls.element_name = getattr(cls, 'element_name',
                             _cls_to_element(name))
            cls.plural_name = getattr(cls, 'plural_name',
                             '%ss' % cls.element_name)
            cls.base_url = getattr(cls, 'base_url',
                             '/%s' % cls.plural_name.replace('-', '_'))

            # Auto-add various getters
            def contribute(src, src_name, dest, dest_name):
                if getattr(src, src_name, None):
                    setattr(
                        dest,
                        dest_name.replace('-', '_'),
                        types.MethodType(getattr(src, src_name), None, dest))
            contribute(cls, '_get', Harvest, cls.element_name)
            contribute(cls, '_objects', Harvest, cls.plural_name)
            for parent in getattr(cls, 'parent_items', []):
                contribute(cls, '_sub_get', parent, cls.element_name)
                contribute(cls, '_sub_objects', parent, cls.plural_name)

_item_cache = {}
def _cache_item(f):
    @functools.wraps(f)
    def wrapper(cls, obj, id, no_cache=False):
        cache_key = '%s(%s)' % (cls.__name__, id)
        result = _item_cache.get(cache_key)
        if result is None or no_cache:
            result = f(cls, obj, id)
            _item_cache[cache_key] = result
        return result
    return wrapper

def _cache_items(f):
    @functools.wraps(f)
    def wrapper(cls, obj, **kwargs):
        no_cache = kwargs.pop('no_cache', False)
        
        if kwargs:
            cache_key = None
        else:
            cache_key = '%s(all)' % cls.__name__
            
        # Check for cached list
        result = _item_cache.get(cache_key, [])
        if result and not no_cache:
            for item in result:
                yield item
            return

        for item in f(cls, obj, **kwargs):
            if hasattr(item, 'id'):
                _item_cache['%s(%s)' % (cls.__name__, item.id)] = item
            if cache_key:
                result.append(item)
            yield item

        # Only cache if all items consumed
        if cache_key:
            _item_cache[cache_key] = result
    return wrapper
                
class HarvestItemGettable(HarvestItemBase):
    __metaclass__ = _GettableType
    _abstract = True

    parent_items = []

    @classmethod
    @_cache_item
    def _sub_get(cls, parent, id):
        url = _build_url(parent.base_url, parent.id, cls.base_url, id)
        return parent.harvest._get_item(cls, url)
        
    @classmethod
    @_cache_items
    def _sub_objects(cls, parent, **params):
        params = dict((k.lstrip('_'), v) for k, v in params.items())
        url = _build_url(parent.base_url, parent.id, cls.base_url, **params)
        return parent.harvest._get_items(cls, url)
    
class HarvestPrimaryGettable(HarvestItemGettable):    
    _abstract = True
    
    get_url = None
    
    @classmethod
    @_cache_item
    def _get(cls, harvest, id):
        url = _build_url(cls.get_url or cls.base_url, id)
        return harvest._get_item(cls, url)
        
    @classmethod
    @_cache_items
    def _objects(cls, harvest, **params):
        url = _build_url(cls.base_url, **params)
        return harvest._get_items(cls, url)
    
    
# Harvest item classes
# http://www.getharvest.com/api

class Entry(HarvestPrimaryGettable):
    element_name = 'day_entry'
    plural_name = 'day_entries'
    base_url = '/daily'
    get_url = '/daily/show'

    def __str__(self):
        return 'task %(hours)0.02f hours for project %(project_id)d' % self.__dict__
    
class Client(HarvestPrimaryGettable):
    def projects(self):
        return Project._objects(self.harvest, client=self.id)

    def invoices(self):
        return Invoice._objects(self.harvest, client=self.id)
    
class Contact(HarvestPrimaryGettable):
    parent_items = [Client]

    def __str__(self):
        return 'Contact: %(first_name)s %(last_name)s' % self.__dict__
    
class Project(HarvestPrimaryGettable):
    def entries(self, start, end, **filters):
        filters.update({'from': start, 'to': end})
        url = _build_url(self.base_url, self.id, 'entries', **filters)
        return self.harvest._get_items(Entry, url)
    
    def expenses(self, start, end, **filters):
        filters.update({'from': start, 'to': end})
        url = _build_url(self.base_url, self.id, 'expenses', **filters)
        return self.harvest._get_items(Expense, url)
    
class Task(HarvestPrimaryGettable):
    pass

class User(HarvestPrimaryGettable):
    base_url = '/people'

    def __str__(self):
        return 'User: %(first_name)s %(last_name)s' % self.__dict__
    
class ExpenseCategory(HarvestPrimaryGettable):
    plural = 'expense-categories'

class Expense(HarvestItemGettable):
    parent_items = [User]
    
class UserAssignment(HarvestItemGettable):
    parent_items = [Project]
    
    def __str__(self):
        return 'user %(user_id)s for project %(project_id)d' % self.__dict__
    
class TaskAssignment(HarvestItemGettable):
    parent_items = [Project]
    
    def __str__(self):
<<<<<<< HEAD
        return 'invoice %d for client %d' % (self.id, self.client_id)

    @property
    def csv_line_items(self):
        '''
        Invoices from lists omit csv-line-items

        '''
        if not hasattr(self, '_csv_line_items'):
            url = '%s/%s' % (self.base_url, self.id)
            self._csv_line_items = self.harvest._get_element_values( url, self.element_name ).next().get('csv-line-items', '')
        return self._csv_line_items

    @csv_line_items.setter
    def csv_line_items(self, val):
        self._csv_line_items = val

    def line_items(self):
        import csv
        return csv.DictReader(self.csv_line_items.split('\n'))


class Harvest(object):
    def __init__(self,uri,email,password):
        self.uri = uri
        self.headers={
            'Authorization':'Basic '+b64encode('%s:%s' % (email,password)),
            'Accept':'application/xml',
            'Content-Type':'application/xml',
            'User-Agent':'harvest.py',
        }

        # create getters
        for klass in instance_classes:
            self._create_getters( klass )

    def _create_getters(self,klass):
        '''
        This method creates both the singular and plural getters for various
        Harvest object classes.

        '''
        flag_name = '_got_' + klass.element_name
        cache_name = '_' + klass.element_name

        setattr( self, cache_name, {} )
        setattr( self, flag_name, False )

        cache = getattr( self, cache_name )

        def _get_item(id):
            if id in cache:
                return cache[id]
            else:
                url = '%s/%d' % (klass.base_url, id)
                item = self._get_element_values( url, klass.element_name ).next()
                item = klass( self, item )
                cache[id] = item
                return item

        setattr( self, klass.element_name, _get_item )

        def _get_items():
            if getattr( self, flag_name ):
                for item in cache.values():
                    yield item
            else:
                for element in self._get_element_values( klass.base_url, klass.element_name ):
                    item = klass( self, element )
                    cache[ item.id ] = item
                    yield item

                setattr( self, flag_name, True )

        setattr( self, klass.plural_name, _get_items )

    def find_user(self, first_name, last_name):
        for person in self.users():
            if first_name.lower() in person.first_name.lower() and last_name.lower() in person.last_name.lower():
                return person

        return None

    def _time_entries(self,root,start,end):
        url = root + 'entries?from=%s&to=%s' % (start.strftime('%Y%m%d'), end.strftime('%Y%m%d'))

        for element in self._get_element_values( url, 'day-entry' ):
            yield Entry( self, element )

    def _request(self,url):
        request = urllib2.Request( url=self.uri+url, headers=self.headers )
        try:
            r = urllib2.urlopen(request)
            xml = r.read()
            return parseString( xml )
        except urllib2.URLError as e:
            raise HarvestConnectionError(e)

    def _get_element_values(self,url,tagname):
        def get_element(element):
            text = ''.join( n.data for n in element.childNodes if n.nodeType == n.TEXT_NODE )
            try:
                entry_type = element.getAttribute('type')
                if entry_type == 'integer':
                    try:
                        return int( text )
                    except ValueError:
                        return 0
                elif entry_type in ('date','datetime'):
                    return parseDate( text )
                elif entry_type == 'boolean':
                    try:
                        return text.strip().lower() in ('true', '1')
                    except ValueError:
                        return False
                elif entry_type == 'decimal':
                    try:
                        return float( text )
                    except ValueError:
                        return 0.0
                else:
                    return text
            except:
                return text

        xml = self._request(url)
        for entry in xml.getElementsByTagName(tagname):
            value = {}
            for attr in entry.childNodes:
                if attr.nodeType == attr.ELEMENT_NODE:
                    tag = attr.tagName
                    value[tag] = get_element( attr )
=======
        return 'task %(task_id)s for project %(project_id)d' % self.__dict__
    
class Invoice(HarvestPrimaryGettable):
    pass
>>>>>>> origin/new_version

class InvoiceMessage(HarvestItemGettable):
    base_url = '/messages'
    parent_items = [Invoice]
    
class Payment(HarvestItemGettable):
    parent_items = [Invoice]
    
class InvoiceItemCategory(HarvestPrimaryGettable):
    plural_name = 'invoice-item-categories'
    
# HTTPRequest to specify HTTP method
    
class HTTPRequest(urllib2.Request):
  def __init__(self, *args, **kwargs):
    self._method = kwargs.pop('method', None)
    urllib2.Request.__init__(self, *args, **kwargs)

  def get_method(self):
    return self._method or urllib2.Request.get_method(self)
