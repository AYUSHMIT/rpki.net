# Copyright (C) 2012  SPARTA, Inc. a Parsons Company
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND SPARTA DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS.  IN NO EVENT SHALL SPARTA BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
# OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.

__version__ = '$Id$'

from rpki.gui.cacheview.models import Cert
from rpki.gui.cacheview.views import cert_chain
from rpki.gui.app.models import ResourceCert
from rpki.gui.app.glue import list_received_resources
from rpki.irdb.models import ResourceHolderCA
from rpki.irdb import Zookeeper
from rpki.left_right import report_error_elt, list_published_objects_elt
from rpki.x509 import X509

import datetime
import sys
from optparse import OptionParser

Verbose = False


def check_cert(handle, p):
    """Check the expiration date on the X.509 certificates in each element of
    the list.

    The displayed object name defaults to the class name, but can be overridden
    using the `object_name` argument.

    """
    t = p.certificate.getNotAfter()
    if Verbose or t <= expire_time:
        e = 'expired' if t <= now else 'will expire'
        print "%(handle)s's %(type)s %(desc)s %(expire)s on %(date)s" % {
            'handle': handle, 'type': p.__class__.__name__, 'desc': str(p),
            'expire': e, 'date': t}


def check_cert_list(handle, x):
    for p in x:
        check_cert(handle, p)


def check_expire(conf):
    # get certs for `handle'
    cert_set = ResourceCert.objects.filter(parent__issuer=conf)
    for cert in cert_set:
        # look up cert in cacheview db
        obj_set = Cert.objects.filter(repo__uri=cert.uri)
        if not obj_set:
            # since the <list_received_resources/> output is cached, this can
            # occur if the cache is out of date as well..
            print "Unable to locate rescert in rcynic cache: handle=%s uri=%s not_after=%s" % (conf.handle, cert.uri, cert.not_after)
            continue
        obj = obj_set[0]
        cert_list = cert_chain(obj)
        msg = []
        expired = False
        for n, c in cert_list:
            if c.not_after <= expire_time:
                expired = True
                f = '*'
            else:
                f = ' '
            msg.append("%s  [%d] uri=%s ski=%s name=%s expires=%s" % (f, n, c.repo.uri, c.keyid, c.name, c.not_after))
        if expired or Verbose:
            print "%s's rescert from parent %s will expire soon:\n" % (conf.handle, cert.parent.handle)
            print "Certificate chain:"
            print "\n".join(msg)


def check_child_certs(conf):
    """Fetch the list of published objects from rpkid, and inspect the issued
    resource certs (uri ending in .cer).

    """
    z = Zookeeper(handle=conf.handle)
    req = list_published_objects_elt.make_pdu(action="list",
                                              tag="list_published_objects",
                                              self_handle=conf.handle)
    pdus = z.call_rpkid(req)
    for pdu in pdus:
        if isinstance(pdu, report_error_elt):
            print "rpkid reported an error: %s" % pdu.error_code
        elif isinstance(pdu, list_published_objects_elt):
            if pdu.uri.endswith('.cer'):
                cert = X509()
                cert.set(Base64=pdu.obj)
                t = cert.getNotAfter()
                if Verbose or t <= expire_time:
                    e = 'expired' if t <= now else 'will expire'
                    print "%(handle)s's rescert for Child %(child)s %(expire)s on %(date)s uri=%(uri)s subject=%(subject)s" % {
                        'handle': conf.handle,
                        'child': pdu.child_handle,
                        'uri': pdu.uri,
                        'subject': cert.getSubject(),
                        'expire': e,
                        'date': t}


usage = '%prog [ -vV ] [ handle1 handle2... ]'

description = """Generate a report detailing all RPKI/BPKI certificates which
are due for impending expiration.  If no resource handles are specified, a
report about all resource handles hosted by the local rpkid instance will be
generated."""

parser = OptionParser(usage, description=description)
parser.add_option('-v', '--verbose', help='enable verbose output',
                    action='store_true', dest='verbose',
                    default=False)
parser.add_option('-V', '--version', help='display script version',
                    action='store_true', dest='version', default=False)
parser.add_option('-t', '--expire-time',
                  dest='expire_days',
                  default=14,
                  metavar='DAYS',
                  help='specify the number of days in the future to check [default: %default]')
(options, args) = parser.parse_args()
if options.version:
    print __version__
    sys.exit(0)
Verbose = options.verbose
now = datetime.datetime.utcnow()
expire_time = now + datetime.timedelta(options.expire_days)

# if not arguments are given, query all resource holders
qs = ResourceHolderCA.objects.all() if not args else ResourceHolderCA.objects.filter(handle__in=args)

# check expiration of certs for all handles managed by the web portal
for h in qs:
    # force cache update
    if Verbose:
        print 'Updating received resources cache for %s' % h.handle
    list_received_resources(sys.stdout, h)

    check_cert(h.handle, h)

    # HostedCA is the ResourceHolderCA cross certified under ServerCA, so check
    # the ServerCA expiration date as well
    check_cert(h.handle, h.hosted_by)
    check_cert(h.handle, h.hosted_by.issuer)

    check_cert_list(h.handle, h.bscs.all())
    check_cert_list(h.handle, h.parents.all())
    check_cert_list(h.handle, h.children.all())
    check_cert_list(h.handle, h.repositories.all())

    check_expire(h)
    check_child_certs(h)

sys.exit(0)
