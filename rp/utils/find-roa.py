#!/usr/bin/env python
#
# $Id$
# 
# Copyright (C) 2014 Dragon Research Labs ("DRL")
# 
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
# 
# THE SOFTWARE IS PROVIDED "AS IS" AND DRL DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS.  IN NO EVENT SHALL DRL BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
# OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.

"""
Replacement for old C-based find_roa program.  Write real doc later.
"""

import os
import sys
import base64
import argparse
import rpki.POW
import rpki.oids


def check_dir(s):
  if os.path.isdir(s):
    return os.path.abspath(s)
  else:
    raise argparse.ArgumentTypeError("%r is not a directory" % s)


def filename_to_uri(filename):
  if not filename.startswith(args.rcynic_dir):
    raise ValueError
  return "rsync://" + filename[len(args.rcynic_dir):].lstrip("/")

def uri_to_filename(uri):
  if not uri.startswith("rsync://"):
    raise ValueError
  return os.path.join(args.rcynic_dir, uri[len("rsync://"):])


class Prefix(object):
  """
  One prefix parsed from the command line.
  """

  def __init__(self, val):
    addr, length = val.split("/")
    length, sep, maxlength = length.partition("-")
    self.prefix = rpki.POW.IPAddress(addr)
    self.length = int(length)
    self.maxlength = int(maxlength) if maxlength else self.length
    if self.maxlength < self.length or self.length < 0 or self.length > self.prefix.bits:
      raise ValueError
    if self.prefix & ((1 << (self.prefix.bits - self.length)) - 1) != 0:
      raise ValueError

  def matches(self, roa):
    return any(self.prefix == prefix and
               self.length == length and
               (not args.match_maxlength or
                self.maxlength == maxlength or
                (maxlength is None and
                 self.length == self.maxlength))
               for prefix, length, maxlength in roa.prefixes)


class ROA(rpki.POW.ROA):
  """
  Aspects of a ROA that we care about.
  """

  @classmethod
  def parse(cls, fn):
    assert fn.startswith(args.rcynic_dir)
    self = cls.derReadFile(fn)
    self.fn = fn
    self.extractWithoutVerifying()
    v4, v6 = self.getPrefixes()
    self.prefixes = (v4 or ()) + (v6 or ())
    return self

  @property
  def uri(self):
    return filename_to_uri(self.fn)

  @property
  def formatted_prefixes(self):
    for prefix in self.prefixes:
      if prefix[2] is None or prefix[1] == prefix[2]:
        yield "%s/%d" % (prefix[0], prefix[1])
      else:
        yield "%s/%d-%d" % (prefix[0], prefix[1], prefix[2])

  def __str__(self):
    prefixes = " ".join(self.formatted_prefixes)
    return "ASN %s prefix(es) %s" % (self.getASID(), prefixes)

  def show(self):
    print "%s %s" % (self, self.uri if args.show_uris else self.fn)

  def show_expiration(self):
    print self
    x = self.certs()[0]
    uri = self.uri
    while uri is not None:
      print x.getNotAfter(), uri
      for uri in x.getAIA() or ():
        if uri.startswith("rsync://"):
          break
      else:
        break
      fn = uri_to_filename(uri)
      if not os.path.exists(fn):
        print "***** MISSING ******", uri
        break
      x = rpki.POW.X509.derReadFile(fn)
    print


parser = argparse.ArgumentParser(description = __doc__)
parser.add_argument("--match-maxlength", action = "store_true", help = "pay attention to maxLength values")
parser.add_argument("--show-expirations", action = "store_true", help = "show ROA chain expiration dates")
parser.add_argument("--show-uris", action = "store_true", help = "show URIs instead of filenames")
parser.add_argument("rcynic_dir", type = check_dir, help = "rcynic authenticated output directory")
parser.add_argument("prefixes", type = Prefix, nargs = "+", help = "ROA prefix(es) to match")
args = parser.parse_args()


for root, dirs, files in os.walk(args.rcynic_dir):
  for fn in files:
    if fn.endswith(".roa"):
      roa = ROA.parse(os.path.join(root, fn))
      if any(prefix.matches(roa) for prefix in args.prefixes):
        if args.show_expirations:
          roa.show_expiration()
        else:
          roa.show()
