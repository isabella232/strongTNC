# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import, unicode_literals

from django.utils import timezone

import pytest
from model_mommy import mommy

from apps.core.models import Session, WorkItem
from apps.core.types import WorkItemType
from apps.swid.models import Tag, EntityRole, Entity
from apps.filesystem.models import File, Directory
from apps.swid import utils
from apps.swid import views


### FIXTURES ###

@pytest.fixture
def swidtag(request, transactional_db):
    """
    Create and return a apps.swid.models.Tag instance based on the specified file.

    This requires the test using this fixture to be parametrized with a
    'filename' argument that specifies the filename of the SWID tag test file
    inside `tests/test_tags/`.

    """
    filename = request.getfuncargvalue('filename')
    with open('tests/test_tags/%s' % filename, 'r') as f:
        tag_xml = f.read()
        return utils.process_swid_tag(tag_xml)[0]


@pytest.fixture
def session(transactional_db):
    test_session = mommy.make(Session, time=timezone.now())
    workitem = mommy.make(WorkItem, type=WorkItemType.SWIDT,
                          session=test_session)

    with open('tests/test_tags/multiple-swid-tags.txt', 'r') as f:
        workitem.result = f.read()
        workitem.save()

    return test_session


### SWID XML PROCESSING TESTS ###

@pytest.mark.parametrize(['filename', 'package_name'], [
    ('strongswan.short.swidtag', 'strongswan'),
    ('strongswan.full.swidtag', 'strongswan'),
    ('cowsay.short.swidtag', 'cowsay'),
    ('cowsay.full.swidtag', 'cowsay'),
    ('strongswan-tnc-imcvs.short.swidtag', 'strongswan-tnc-imcvs'),
    ('strongswan-tnc-imcvs.full.swidtag', 'strongswan-tnc-imcvs'),
])
def test_tag_name(swidtag, filename, package_name):
    assert swidtag.package_name == package_name


@pytest.mark.parametrize(['filename', 'unique_id'], [
    ('strongswan.short.swidtag', 'debian_7.4-x86_64-strongswan-4.5.2-1.5+deb7u3'),
    ('strongswan.full.swidtag', 'debian_7.4-x86_64-strongswan-4.5.2-1.5+deb7u3'),
    ('cowsay.short.swidtag', 'debian_7.4-x86_64-cowsay-3.03+dfsg1-4'),
    ('cowsay.full.swidtag', 'debian_7.4-x86_64-cowsay-3.03+dfsg1-4'),
    ('strongswan-tnc-imcvs.short.swidtag', 'fedora_19-x86_64-strongswan-tnc-imcvs-5.1.2-4.fc19'),
    ('strongswan-tnc-imcvs.full.swidtag', 'fedora_19-x86_64-strongswan-tnc-imcvs-5.1.2-4.fc19'),
])
def test_tag_unique_id(swidtag, filename, unique_id):
    assert swidtag.unique_id == unique_id


@pytest.mark.parametrize(['filename', 'version'], [
    ('strongswan.short.swidtag', '4.5.2-1.5+deb7u3'),
    ('strongswan.full.swidtag', '4.5.2-1.5+deb7u3'),
    ('cowsay.short.swidtag', '3.03+dfsg1-4'),
    ('cowsay.full.swidtag', '3.03+dfsg1-4'),
    ('strongswan-tnc-imcvs.short.swidtag', '5.1.2-4.fc19'),
    ('strongswan-tnc-imcvs.full.swidtag', '5.1.2-4.fc19'),
])
def test_tag_version(swidtag, filename, version):
    assert swidtag.version == version


@pytest.mark.parametrize(['filename', 'tagroles'], [
    ('strongswan.short.swidtag', [EntityRole.TAGCREATOR]),
    ('strongswan.full.swidtag', [EntityRole.TAGCREATOR, EntityRole.PUBLISHER]),
    ('strongswan.full.swidtag.combinedrole',
        [EntityRole.TAGCREATOR, EntityRole.PUBLISHER, EntityRole.LICENSOR]),
    ('cowsay.short.swidtag', [EntityRole.TAGCREATOR]),
    ('cowsay.full.swidtag', [EntityRole.TAGCREATOR, EntityRole.LICENSOR]),
    ('strongswan-tnc-imcvs.short.swidtag', [EntityRole.TAGCREATOR]),
    ('strongswan-tnc-imcvs.full.swidtag', [EntityRole.TAGCREATOR]),
])
def test_tag_entity_roles(swidtag, filename, tagroles):
    roles = [i.role for i in swidtag.entityrole_set.all()]
    assert sorted(roles) == sorted(tagroles)


@pytest.mark.parametrize('filename', [
    'strongswan.short.swidtag',
    'strongswan.full.swidtag',
    'cowsay.short.swidtag',
    'cowsay.full.swidtag',
    'strongswan-tnc-imcvs.short.swidtag',
    'strongswan-tnc-imcvs.full.swidtag',
])
def test_tag_xml(swidtag, filename):
    with open('tests/test_tags/%s' % filename, 'r') as swid_file:
        swid_tag_xml = swid_file.read()
        swid_tag_xml_pretty = utils.prettify_xml(swid_tag_xml.decode('utf8'))
        assert swidtag.swid_xml == swid_tag_xml_pretty


@pytest.mark.parametrize(['filename', 'directories', 'files', 'filecount'], [
    ('strongswan.full.swidtag', ['/usr/share/doc/strongswan'], [
        'README.gz',
        'CREDITS.gz',
        'README.Debian.gz',
        'NEWS.Debian.gz',
        'changelog.gz',
    ], 7),
    ('cowsay.full.swidtag', ['/usr/share/cowsay/cows', '/usr/games'], [
        'cowsay',
        'cowthink',
        'vader-koala.cow',
        'elephant-in-snake.cow',
        'ghostbusters.cow',
    ], 61),
    ('strongswan-tnc-imcvs.full.swidtag', ['/usr/lib64/strongswan', '/usr/lib64/strongswan/imcvs'], [
        'libradius.so.0',
        'libtnccs.so.0.0.0',
        'imv-attestation.so',
        'imv-test.so',
    ], 35),
])
def test_tag_files(swidtag, filename, directories, files, filecount):
    assert File.objects.filter(name__in=files).count() == len(files)
    assert Directory.objects.filter(path__in=directories).count() == len(directories)
    assert swidtag.files.count() == filecount


@pytest.mark.parametrize('filename', [
    'strongswan.full.swidtag',
])
def test_tag_replacement(swidtag, filename):
    with open('tests/test_tags/strongswan.full.swidtag.singleentity') as f:
        xml = f.read()
        tag, replaced = utils.process_swid_tag(xml)
        assert tag.software_id == swidtag.software_id
        assert replaced == True
        assert len(tag.entity_set.all()) == 1


@pytest.mark.django_db
@pytest.mark.parametrize('filename', [
    'strongswan.full.swidtag.notagcreator',
    'strongswan.full.swidtag.nouniqueid',
    'strongswan.full.swidtag.emptyuniqueid',
    'strongswan.full.swidtag.emptyregid'
])
def test_invalid_tags(filename):
    with open('tests/test_tags/invalid_tags/%s' % filename) as f:
        xml = f.read()
        # an invalid tag should raise an ValueError
        with pytest.raises(ValueError):
            tag, replaced = utils.process_swid_tag(xml)
        assert len(Tag.objects.all()) == 0
        assert len(Entity.objects.all()) == 0


@pytest.mark.parametrize('filename',[
    'strongswan.full.swidtag',
])
def test_entity_name_update(swidtag, filename):
    assert(Entity.objects.count() == 1)
    new_xml = swidtag.swid_xml.replace('name="strongSwan"', 'name="strongswan123"')
    tag, replaced = utils.process_swid_tag(new_xml)
    assert(Entity.objects.count() == 1)
    assert(Tag.objects.count() == 1)
    assert(replaced)

    new_xml = swidtag.swid_xml.replace('name="strongSwan" regid="regid.2004-03.org.strongswan"',
                                       'name="strongSwan" regid="regid.2005-03.org.strongswan"')
    tag, replaced = utils.process_swid_tag(new_xml)

    # a new entity with a different regid should be created
    # also a new tag is create because the software id has changed
    assert(Entity.objects.count() == 2)
    assert(Tag.objects.count() == 2)
    assert(not replaced)


@pytest.mark.parametrize('value', ['publisher', 'licensor', 'tagcreator'])
def test_valid_role(value):
    try:
        EntityRole.xml_attr_to_choice(value)
    except ValueError:
        pytest.fail('Role %s should be valid.' % value)


def test_invalid_role():
    with pytest.raises(ValueError):
        EntityRole.xml_attr_to_choice('licensee')
