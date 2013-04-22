import base64
import simplejson
import binascii
from datetime import datetime
from django.db import models

class BinaryField(models.Field):
    description = "Raw binary data for SQLite"

    def __init__(self, *args, **kwargs):
        kwargs['editable'] = False
        super(BinaryField, self).__init__(*args, **kwargs)

    def db_type(self, connection):
        """Internal database field type."""
        return 'blob'

class HashField(BinaryField):
    __metaclass__ = models.SubfieldBase

    def to_python(self, value):
        return binascii.hexlify(value)

    def get_prep_value(self, value):
        return binascii.unhexlify(value)

class Action(object):
    NONE = 0
    ALLOW = 1
    ISOLATE = 2
    BLOCK = 3

class Product(models.Model):
    """
    Platform (f.e Android or Ubuntu)
    """
    id = models.AutoField(primary_key=True)
    name = models.TextField()

    def __unicode__(self):
        return self.name

    def __json__(self):
        return simplejson.dumps({
            'id': self.id,
            'name': self.name
            })

    class Meta:
        db_table = u'products'

class Device(models.Model):
    """
    An Android Device identified by its AndroidID
    """
    id = models.AutoField(primary_key=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    product = models.ForeignKey(Product, related_name='devices')


    def __unicode__(self):
        return '%s (%s)' % (self.description, self.value[:10])

    def get_group_set(self):
        groups = []
        for g in self.groups.all():
            groups.append(g)
            groups += g.get_parents()

        groups = set(groups)
        return groups

    def is_due_for(self, enforcement):
        try:
            last_meas = Measurement.objects.filter(device=self).latest('time')
            result = Result.objects.get(measurement=last_meas,
                    policy=enforcement.policy)
        except Measurement.DoesNotExist:
            return True
        except Result.DoesNotExist:
            return True

        age = datetime.today() - last_meas.time

        #See tannerli/cygnet-doc#35 for how previous results should be tested
        if age.days >= enforcement.max_age: #or result.result != 0:
            return True

        return False

    def create_work_items(self, measurement):

        groups = self.get_group_set()
        enforcements = []
        for group in groups:
           enforcements += group.enforcements.all()

        minforcements=[]

        while enforcements:
            emin = enforcements.pop()
            for e in enforcements:
                if emin.policy == e.policy:
                    emin = min(emin,e, key=lambda x: x.max_age)
                    if emin == e:
                        enforcements.remove(e)

            minforcements.append(emin)

        for enforcement in minforcements:
            if self.is_due_for(enforcement):
                enforcement.policy.create_work_item(enforcement, measurement)

        return groups

    class Meta:
        db_table = u'devices'

class Group(models.Model):
    """
    Management group of devices
    """
    id = models.AutoField(primary_key=True)
    name = models.CharField(unique=True, max_length=50)
    members = models.ManyToManyField(Device, related_name='groups',blank=True)
    product_defaults = models.ManyToManyField(Product, related_name='default_groups', blank=True)
    parent = models.ForeignKey('self', related_name='membergroups', null=True,
            blank=True, on_delete=models.CASCADE)

    def __unicode__(self):
        return self.name

    def get_parents(self):
        if not self.parent:
            return []

        return [self.parent] + self.parent.get_parents()

    class Meta:
        db_table = u'groups'

class Directory(models.Model):
    """
    Unix-style directory path
    """
    id = models.AutoField(primary_key=True)
    path = models.TextField(unique=True)

    def __unicode__(self):
        return self.path

    class Meta:
        db_table = u'directories'
    

class File(models.Model):
    """
    Filename
    """
    id = models.AutoField(primary_key=True)
    directory = models.ForeignKey(Directory, db_column='dir',
            related_name='files', on_delete=models.CASCADE)
    name = models.TextField()

    def __unicode__(self):
        return '%s/%s' % (self.directory.path, self.name)

    def __json__(self):
        return simplejson.dumps({
            'id' : self.id,
            'name' : self.name,
            'dir' : self.directory.path,
            })

    class Meta:
        db_table = u'files'

class Algorithm(models.Model):
    """
    A hashing algorithm
    """
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=20)

    def __unicode__(self):
        return self.name

    def __json__(self):
        return simplejson.dumps({
            'id' : self.id,
            'name' : self.name,
            })

    class Meta:
        db_table = u'algorithms'

class FileHash(models.Model):
    """
    SHA-1 or similar filehash
    """
    id = models.AutoField(primary_key=True)
    file = models.ForeignKey(File, db_column='file', related_name='hashes',
            on_delete=models.CASCADE)
    product = models.ForeignKey(Product, db_column='product')
    key = models.IntegerField(null=False, default=0)
    algorithm = models.ForeignKey(Algorithm, db_column='algo',
            on_delete=models.PROTECT)
    hash = HashField(db_column='hash')

    class Meta:
        db_table = u'file_hashes'

    def __unicode__(self):
        return '%s (%s)' % (self.hash, self.algorithm)

    def __json__(self):
        return simplejson.dumps({
            'file' : self.file.__json__(),
            'product' : self.product.__json__(),
            'key' : self.key,
            'algo' : self.algorithm.__json__(),
            'hash' : base64.encodestring(self.hash.__str__()),
            })


class Package(models.Model):
    """
    aptitude Package name
    """
    id = models.AutoField(primary_key=True)
    name = models.TextField(unique=True)
    blacklist = models.IntegerField(blank=True, default=0)

    def __unicode__(self):
        return self.name

    class Meta:
        db_table = u'packages'

class Version(models.Model):
    """
    Version number string of a package
    """
    id = models.AutoField(primary_key=True)
    package = models.ForeignKey(Package, db_column='package',
            on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name='versions',
            db_column='product', on_delete=models.CASCADE)
    release = models.TextField()
    security = models.BooleanField(default=0)
    time = models.DateTimeField(datetime.today())
    blacklist = models.IntegerField(null=True, blank=True)

    def __unicode__(self):
        return self.release

    class Meta:
        db_table = u'versions'

class Policy(models.Model):
    """
    Instance of a policy. Defines a specific check
    """
    id = models.AutoField(primary_key=True)
    type = models.IntegerField()
    name = models.CharField(unique=True, max_length=100)
    argument = models.TextField()
    fail = models.IntegerField(blank=True)
    noresult = models.IntegerField(blank=True)
    file = models.ForeignKey(File, null=True, related_name='policies',
            on_delete=models.PROTECT)
    dir = models.ForeignKey(Directory, null=True, related_name='policies',
            on_delete=models.PROTECT)

    def create_work_item(self, enforcement, measurement):
        item = WorkItem()
        item.result = None
        item.type = self.type
        item.recommendation = None
        item.argument = self.argument
        item.enforcement = enforcement
        item.measurement = measurement
        
        item.fail = self.fail
        if enforcement.fail is not None:
            item.fail = enforcement.fail

        item.noresult = self.noresult
        if enforcement.noresult is not None:
            item.noresult = enforcement.noresult

        item.save()

    def __unicode__(self):
        return self.name

    argument_funcs = {
            'FileHash': lambda file: file.id,
            'DirHash': lambda dir: dir.id,
            'ListeningPort': lambda range: range,
            'FileExist': lambda file: file.id,
            'NotFileExist': lambda file: file.id,
            'MissingUpdate': lambda: '',
            'MissingSecurityUpdate': lambda: '',
            'BlacklistedPackage': lambda: '',
            'OSSettings': lambda: '',
            'Deny': lambda: '',
            }

    class Meta:
        db_table = u'policies'
        verbose_name_plural = 'Policies'

class Enforcement(models.Model):
    """
    Rule to enforce a policy on a group
    """
    id = models.AutoField(primary_key=True)
    policy = models.ForeignKey(Policy, related_name='enforcements',
            on_delete=models.CASCADE)
    group = models.ForeignKey(Group, related_name='enforcements',
            on_delete=models.CASCADE)
    max_age = models.IntegerField()
    fail = models.IntegerField(null=True,blank=True)
    noresult = models.IntegerField(null=True,blank=True)

    def __unicode__(self):
        return '%s on %s' % (self.policy.name, self.group.name)

    class Meta:
        db_table = u'enforcements'
        unique_together = (('policy','group'))

class Identity(models.Model):
    id = models.AutoField(primary_key=True)
    type = models.IntegerField()
    data = models.TextField()

    class Meta:
        db_table = u'identities'

class Measurement(models.Model):
    """Result of a TNC measurement."""
    id = models.AutoField(primary_key=True)
    connectionID = models.IntegerField()
    device = models.ForeignKey(Device, related_name='measurements',
        on_delete=models.CASCADE)
    user = models.ForeignKey(Identity, related_name='measurements',
            on_delete=models.CASCADE)
    time = models.DateTimeField()

    class Meta:
        db_table = u'measurements'

class WorkItem(models.Model):
    id = models.AutoField(primary_key=True)
    enforcement = models.ForeignKey(Enforcement, on_delete=models.CASCADE)
    measurement = models.ForeignKey(Measurement, related_name='workitems',
            on_delete=models.CASCADE)
    type = models.IntegerField(null=False, blank=False)
    argument = models.TextField()
    fail = models.IntegerField(null=True,blank=True)
    noresult = models.IntegerField(null=True,blank=True)
    result = models.TextField(null=True)
    recommendation = models.IntegerField(null=True,blank=True)

    class Meta:
        db_table = u'workitems'

class Result(models.Model):
    id = models.AutoField(primary_key=True)
    measurement = models.ForeignKey(Measurement, on_delete=models.CASCADE)
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE)
    result = models.TextField()
    recommendation = models.IntegerField()

    class Meta:
        db_table = u'results'

