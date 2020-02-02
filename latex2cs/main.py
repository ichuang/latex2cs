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
    def __init__(self, fn, latex_string=None, verbose=False, extra_filters=None, add_wrap=False):
        self.fn = fn or ""
        self.verbose = verbose
        self.latex_string = latex_string
        self.add_wrap = add_wrap
        self.extra_filters = extra_filters or []
        self.filters = [ self.filter_fix_math,
                         self.filter_fix_section_headers,
                         self.filter_fix_solutions, 
                         self.filter_fix_inline_prompts, 
                         self.process_includepy,
                         self.pp_xml,			# next-to-next-to-last: pretty prints XML into string
                         self.filter_fix_question,	# must be next-to-last, because the result is not XML strict
                         self.add_explanations,
        ]
        self.filters += self.extra_filters
        self.explanations = {}				# csq_explanations are added at the end, after pretty printing, to preserve pp

    def convert(self, ofn="content.md"):
        imdir = "__STATIC__"
        imurl = ""
        imurl_fmt = "CURRENT/{fnbase}"
        if not os.path.exists(imdir):
            os.mkdir(imdir)
        self.p2x = plastex2xhtml(self.fn,
                                 fp=None,
                                 extra_filters=None,
                                 latex_string=self.latex_string,
                                 add_wrap=self.add_wrap,
                                 verbose=self.verbose,
                                 imdir=imdir,
                                 imurl=imurl,
                                 abox=AnswerBox,
                                 imurl_fmt=imurl_fmt,
                                 )
        self.p2x.convert()
        self.xhtml = self.p2x.xhtml
        xhtml = self.xhtml

        for ffn in self.filters:
            xhtml = ffn(xhtml)

        if ofn:
            with codecs.open(ofn, 'w', encoding="utf8") as ofp:
                ofp.write(xhtml)
                print("Wrote %s" % ofn)
        else:
            return xhtml

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
                if self.verbose > 2:
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

    def add_to_question(self, question, new_line):
        '''
        Add a new line to a <question> elment. 
        Handle this by transforming into string, adding, and transfomring back, so
        that elements in the string are not misorderd or otherwise mangled.

        question = etree element
        new_line = str
        '''
        qstr = etree.tostring(question).decode("utf8")
        qstr = qstr.replace("</question>", "%s\n</question>" % new_line)
        new_q = etree.fromstring(qstr)
        question.addprevious(new_q)
        question.getparent().remove(question)
        
    def filter_fix_inline_prompts(self, xhtml):
        '''
        Move inline prompts into question as csq_prompt or csq_prompts
        '''
        xml = self.str2xml(xhtml)
        nprompts = 0
        for question in xml.findall(".//question"):
            prev = question.getprevious()
            if prev is not None and prev.tag=="p" and prev.get("style")=="display:inline":
                prompt = etree.tostring(prev[0]).decode("utf8")
                prev.getparent().remove(prev)
                new_line = 'csq_prompts = ["""%s"""]' % prompt
                self.add_to_question(question, new_line)
                nprompts += 1
        
        if self.verbose:
            print("[latex2cs] moving %s prompts to their following question" % nprompts)
        return etree.tostring(xml).decode("utf8")


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

                    qtext = 'csq_explanation=r"""\n%s"""' % solution_xmlstr
                    qkey = hashlib.sha224(qtext.encode("utf8")).hexdigest()[:20]
                    self.explanations[qkey] = qtext
                    new_line = '[key:%s]' % qkey
                    self.add_to_question(question, new_line)

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
        
    def process_includepy(self, xmlstr):
        '''
        For line like <edxincludepy linenum="87" filename="week1_3_osr.tex">lib/ps1/check_osr2.py</edxincludepy>
        make sure the preload.py has the appropriate imports
        '''
        xml = self.str2xml(xmlstr)
        ninc = 0
        preload_fn = "preload.py"
        for ipy in xml.findall(".//edxincludepy"):
            pyfn = ipy.text.strip()
            mname = os.path.basename(pyfn).split(".py", 1)[0]
            inc = '%s = cs_local_python_import("%s")\n' % (mname, pyfn)
            with open(preload_fn) as prefp:
                preload = prefp.read()
            if not inc in preload:
                preload += "%s" % inc
                with open(preload_fn, 'w') as prefp:
                    prefp.write(preload)
                ninc += 1
            else:
                if self.verbose:
                    print("[latex2cs] include line for %s already in %s" % (pyfn, preload_fn))
            ipy.getparent().remove(ipy)
        if ninc:
            print("[latex2cs] added %d python-code-include lines to %s" % (ninc, preload_fn))

        return etree.tostring(xml).decode("utf8")


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


