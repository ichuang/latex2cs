#!/usr/bin/env python

import os
import re
import sys
import codecs
import hashlib
import optparse
import subprocess
from lxml import etree
from latex2edx.plastexit import plastex2xhtml

from .abox import AnswerBox

# -----------------------------------------------------------------------------

class latex2cs:
    def __init__(self, fn, verbose=False, extra_filters=None):
        self.fn = fn
        self.verbose = verbose
        self.extra_filters = extra_filters or []
        self.filters = [ self.filter_fix_math,
                         self.filter_fix_section_headers,
                         self.filter_fix_solutions, 
                         self.pp_xml,			# next-to-next-to-last: pretty prints XML into string
                         self.filter_fix_question,	# must be next-to-last, because the result is not XML strict
                         self.add_explanations,
        ]
        self.filters += self.extra_filters
        self.explanations = {}				# csq_explanations are added at the end, after pretty printing, to preserve pp

    def convert(self):
        imdir = "."
        imurl = ""
        self.p2x = plastex2xhtml(self.fn,
                                 fp=None,
                                 extra_filters=None,
                                 latex_string=None,
                                 add_wrap=False,
                                 verbose=self.verbose,
                                 imdir=imdir,
                                 imurl=imurl,
                                 abox=AnswerBox,
                                 )
        self.p2x.convert()
        self.xhtml = self.p2x.xhtml
        xhtml = self.xhtml

        for ffn in self.filters:
            xhtml = ffn(xhtml)

        ofn = "content.md"
        with codecs.open(ofn, 'w', encoding="utf8") as ofp:
            ofp.write(xhtml)
            print("Wrote %s" % ofn)

    def str2xml(self, xmlstr):
        '''
        Convert xmlstr to xml in etree representation, without lossing CDATA sections
        Returns xml tree.
        '''
        parser = etree.XMLParser(strip_cdata=False)
        tree = etree.fromstring(xmlstr, parser=parser)
        return tree

    def pp_xml(self, xml):
        '''
        Pretty print XML

        xml : either etree instance, or string

        Returns string
        '''
        # os.popen('xmllint --format -o tmp.xml -','w').write(etree.tostring(xml))
        try:
            p = subprocess.Popen(['xmllint', '--format', '-o', 'tmp.xml', '-'], stdin=subprocess.PIPE)
            if isinstance(xml, str):
                xml = xml.encode("utf8")
            if not isinstance(xml, bytes):
                xml = etree.tostring(xml)
                if self.verbose:
                    print("[latex2cs] ran tostring on xml, producing type %s" % type(xml))
            # print("xml has type %s" % type(xml))
            p.stdin.write(xml)
            p.stdin.close()
            p.wait()
            xml = codecs.open('tmp.xml', encoding="utf8").read()
            xml = xml.encode("utf8")
        except Exception as err:
            print("[xbundle.py] Warning - no xmllint")
            print(err)
            xml = etree.tostring(xml, pretty_print=True)

        xml = xml.decode("utf8")
        if xml.startswith('<?xml '):
            xml = xml.split('\n', 1)[1]
        return xml

    def filter_fix_question(self, xhtml):
        '''
        change <question pythonic="1".*> to <question pythonic>
        xhtml should be a string
        '''
        xhtml = re.sub('<question pythonic="1".*?>', "<question pythonic>", xhtml)
        return xhtml

    def filter_fix_solutions(self, xhtml):
        '''
        move <solution>...</solution> into nearest csq_explanation inside <question>
        '''
        xml = self.str2xml(xhtml)
        nmoved = 0

        for problem in xml.findall(".//problem"):
            for solution in problem.findall(".//solution"):

                bhead = solution.xpath('.//b[text()="Solution:"]')	# remove <b>Solution:</b> and is containing <p>, if present
                if bhead:
                    bhead = bhead[0]
                    bp = bhead.getparent()
                    if bp.tag=="p":
                        bp.getparent().remove(bp)

                solution_xmlstr = self.pp_xml(solution)
                parent = solution.getparent()
                parent.remove(solution)
                cnt = 0
                while (parent.find(".//question") is None) and (cnt < 5) and (parent.find(".//problem") is None):
                    parent = parent.getparent()
                    cnt += 1
                moved = False
                for question in parent.findall(".//question"):
                    if question.get("has_solution"):
                        continue
                    question.set("has_solution", "1")
                    qstr = etree.tostring(question).decode("utf8")

                    qtext = "csq_explanation=r'''\n%s'''" % solution_xmlstr
                    qkey = hashlib.sha224(qtext.encode("utf8")).hexdigest()[:20]
                    self.explanations[qkey] = qtext

                    qstr = qstr.replace("</question>", "[key:%s]\n</question>" % qkey)
                    new_q = etree.fromstring(qstr)
                    question.addprevious(new_q)
                    question.getparent().remove(question)
                    moved = True
                    nmoved += 1
                if not moved:
                    print("[latex2cs] Error!  Could not find question to move solution into: %s" % solution_xmlstr)

        if self.verbose:
            print("[latex2cs] moving %s solutions to their nearest question" % nmoved)
        return etree.tostring(xml).decode("utf8")

    def add_explanations(self, xmlstr):
        '''
        Add csq_explanation assignments back in, at locations where hash keys are placed
        '''
        for key, text in self.explanations.items():
            xmlstr = xmlstr.replace("[key:%s]" % key, text)
        return xmlstr

    def filter_fix_section_headers(self, xhtml):
        '''
        change <big> to <h2>;
        add <h3> for display_name after  <problem>
        '''
        xml = self.str2xml(xhtml)
        for html in xml.findall(".//html"):
            for big in html.findall(".//big"):
                big.tag = "h2"

        for prob in xml.findall(".//problem"):
            h3 = etree.Element("h3")
            h3.text = prob.get("display_name")
            prob.insert(0, h3)
        return etree.tostring(xml).decode("utf8")

    def filter_fix_math(self, xhtml):
        '''
        Put math into span elements with class cs_math_to_render so catsoop's katex routines know to render them as math
        '''
        if 0:
            xhtml = xhtml.replace("[mathjaxinline]", "\\(")
            xhtml = xhtml.replace("[/mathjaxinline]", "\\)")
            xhtml = xhtml.replace("[mathjax]", "\\[")
            xhtml = xhtml.replace("[/mathjax]", "\\]")
        elif 0:
            xhtml = xhtml.replace("[mathjaxinline]", '<span class="cs_math_to_render cs_mathjax">')
            xhtml = xhtml.replace("[/mathjaxinline]", "</span>")
            xhtml = xhtml.replace("[mathjax]", '<span class="cs_math_to_render cs_mathjax">')
            xhtml = xhtml.replace("[/mathjax]", "</span>")
        else:
            xhtml = xhtml.replace("[mathjaxinline]", '<math>')
            xhtml = xhtml.replace("[/mathjaxinline]", "</math>")
            xhtml = xhtml.replace("[mathjax]", '<displaymath>')
            xhtml = xhtml.replace("[/mathjax]", "</displaymath>")
        return xhtml
        

# -----------------------------------------------------------------------------

def CommandLine():
    import pkg_resources  # part of setuptools
    version = pkg_resources.require("latex2cs")[0].version
    parser = optparse.OptionParser(usage="usage: %prog [options] filename.tex",
                                   version="%prog version " + version)
    parser.add_option('-v', '--verbose',
                      dest='verbose',
                      default=False, action='store_true',
                      help='verbose error messages')
    (opts, args) = parser.parse_args()

    if len(args) < 1:
        print('latex2cs: wrong number of arguments')
        parser.print_help()
        sys.exit(-2)
    fn = args[0]

    l2c = latex2cs(fn, verbose=opts.verbose)
    l2c.convert()


