#!/usr/bin/env python

import os, sys, glob, shutil
from BeautifulSoup import BeautifulSoup, Tag, NavigableString

import conf

def convert(filename, destdir):
    fh = open(filename)
    text = fh.read()
    fh.close()
    
    soup = BeautifulSoup(text)
    addAnchors(soup)
    convertNavigation(soup)
    convertPre(soup)
    
    if destdir:
        if not os.path.exists(destdir):
            os.mkdir(destdir)
        outfile = os.path.join(destdir, os.path.basename(filename))
    else:
        outfile = filename
    fh = open(outfile, "w")
    fh.write(soup.prettify())
    fh.close()

def addAnchors(soup):
    results = soup.findAll("div", "section")
    for result in results:
        #print result.name
        #print result["id"]
        #print result.attrs
        tag = Tag(soup, "a", attrs=[("name", result["id"])])
        result.insert(0, tag)

def convertNavigation(soup):
    """Change the navigation from a css-styled ul to a table
    
    The css lays out two separate sections, one on the left side and one on the
    right side.  This is mimicked by a two column table with the right column
    using an "align=right" entity.
    """
    nav_lists = soup.findAll("div", "related")
    for nav in nav_lists:
        #print nav
        items = nav.findAll("li", attrs={"class": "right"})
        items.reverse()
        #print "items: %s" % items
        right = Tag(soup, "p")
        for item in items:
            # Remove the item so the later findAll will only find those list
            # items that haven't already been processed.
            item.extract()
            
            #print "contents (%d): %s" % (len(item.contents), item.contents)
            # Have to iterate over a copy because the append operation rips the
            # element out of the contents list and messes up the loop
            copy = item.contents[:]
            for a in copy:
                #print "a = %s" % a
                right.append(a)
                
        items = nav.findAll("li")
        left = Tag(soup, "p")
        for item in items:
            copy = item.contents[:]
            for a in copy:
                #print "a = %s" % a
                left.append(a)
        
        table = Tag(soup, "table")
        tr = Tag(soup, "tr")
        table.append(tr)
        td = Tag(soup, "td", attrs=[("width", "50%")])
        tr.append(td)
        td.append(left)
        td = Tag(soup, "td", attrs=[("width", "50%"), ("align", "right")])
        tr.append(td)
        td.append(right)
        
        nav.replaceWith(table)
        #print newlist.prettify()
        #print newlist

def convertPre(soup):
    """The pre blocks need converting because they use <span> tags which
    confuse the parser.
    
    Somehow need to strip out the span tags from within the <pre> tags.
    """
    pass


def convertAll(dirname, func, destdir):
    files = glob.glob("%s/*.html" % dirname)
    for file in files:
        print(file)
        func(file, destdir)
    
    if destdir:
        copyStatic(dirname, destdir)

def copyStatic(dirname, destdir):
    """Copy the static files to the destination directory"""
    for subdir in glob.glob("%s/_*" % dirname):
        if os.path.isdir(subdir):
            destsubdir = os.path.join(destdir, os.path.basename(subdir))
            if not os.path.exists(destsubdir):
                os.mkdir(destsubdir)
            for src in glob.glob("%s/*" % subdir):
                print "cp %s %s" % (src, os.path.join(destsubdir, os.path.basename(src)))
                shutil.copy(src, os.path.join(destsubdir, os.path.basename(src)))
    for src in glob.glob("%s/%s.*" % (dirname, conf.htmlhelp_basename)):
        print "cp %s %s" % (src, os.path.join(destdir, os.path.basename(src)))
        shutil.copy(src, os.path.join(destdir, os.path.basename(src)))
    

if __name__ == "__main__":
    from optparse import OptionParser
    usage="usage: %prog [options] file [files...]"
    parser=OptionParser(usage=usage)
    parser.add_option("-o", action="store", dest="outdir", default="", help="Specify the directory for output files")
    (options, args) = parser.parse_args()
    
    for arg in args:
        if os.path.isdir(arg):
            convertAll(arg, convert, options.outdir)
        else:
            convert(arg, options.outdir)
