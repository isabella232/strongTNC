# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import, unicode_literals

from datetime import timedelta, datetime

from django.utils import timezone
from django.db import models

from apps.core.fields import EpochField
from apps.core.models import Result
from apps.core.types import Action


class Product(models.Model):
    """
    The platform (e.g. Android or Ubuntu).
    """
    name = models.CharField(max_length=255, db_index=True)

    class Meta:
        db_table = 'products'
        ordering = ('name',)

    def __unicode__(self):
        return self.name

    def list_repr(self):
        """
        String representation in lists
        """
        return self.name


class Device(models.Model):
    """
    An Android Device identified by its AndroidID.
    """
    value = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True, default='')
    product = models.ForeignKey(Product, related_name='devices', db_column='product')
    created = EpochField(null=True, blank=True)
    trusted = models.BooleanField(default=False)

    class Meta:
        db_table = 'devices'
        ordering = ('description',)

    def __unicode__(self):
        if self.description:
            return '%s (%s)' % (self.description, self.value[:10])
        else:
            return self.value

    def list_repr(self):
        """
        String representation in lists
        """
        if self.description:
            return '%s (%s)' % (self.description, self.value[:10])
        else:
            return self.value

    def get_group_set(self):
        """
        Get all groups of the device
        """
        groups = []
        for g in self.groups.all():
            groups.append(g)
            groups += g.get_parents()

        groups = set(groups)
        return groups

    def get_inherit_set(self):
        """
        Get the groups which the device has inherited
        """
        group_set = self.get_group_set()
        for group in (group_set & set(self.groups.all())):
            group_set.remove(group)

        return group_set

    def is_due_for(self, enforcement):
        """
        Check if the device needs to perform the measurement defined by the
        enforcement
        """
        try:
            result = Result.objects.filter(session__device=self,
                                           policy=enforcement.policy).latest()
        except Result.DoesNotExist:
            return True

        deadline = timezone.now() - timedelta(seconds=enforcement.max_age)

        if result.session.time < deadline or (result.recommendation != Action.ALLOW):
            return True

        return False

    def create_work_items(self, session):
        """
        Creates workitems for every policy that is due
        """

        enforcements = []
        for group in self.get_group_set():
            enforcements += group.enforcements.all()

        minforcements = []

        while enforcements:
            emin = enforcements.pop()
            for e in enforcements:
                if emin.policy == e.policy:
                    emin = min(emin, e, key=lambda x: x.max_age)
                    if emin == e:
                        enforcements.remove(e)

            minforcements.append(emin)

        for enforcement in minforcements:
            if self.is_due_for(enforcement):
                enforcement.policy.create_work_item(enforcement, session)

    def get_sessions_in_range(self, from_timestamp, to_timestamp):
        dateobj_from, dateobj_to = map(datetime.utcfromtimestamp, [from_timestamp, to_timestamp])
        return self.sessions.filter(time__lte=dateobj_to, time__gte=dateobj_from).order_by('-time')


class Group(models.Model):
    """
    Group of devices, for management purposes.
    """
    name = models.CharField(max_length=50)
    devices = models.ManyToManyField(Device, related_name='groups', blank=True, db_table='groups_members')
    product_defaults = models.ManyToManyField(Product, related_name='default_groups', blank=True)
    parent = models.ForeignKey('self', related_name='membergroups', null=True,
            blank=True, db_column='parent')

    class Meta:
        db_table = 'groups'
        ordering = ('name',)

    def __unicode__(self):
        return self.name

    def list_repr(self):
        """
        String representation in lists
        """
        return self.name

    def get_parents(self):
        """
        Recursively get all parent groups.
        """
        if not self.parent:
            return []
        return [self.parent] + self.parent.get_parents()

    def get_children(self):
        """
        Recursively get all child groups.
        """
        result = list(Group.objects.filter(parent=self))
        for child in result:
            result += list(child.get_children())

        return result
