#!/usr/bin/env python

import os
import re
import sys
import codecs
import hashlib
import argparse
import subprocess
from lxml import etree
from latex2edx.plastexit import plastex2xhtml

from .abox import AnswerBox

# -----------------------------------------------------------------------------

class latex2cs:
    def __init__(self, fn, latex_string=None, verbose=False, extra_filters=None, add_wrap=False, lib_dir=".", do_not_copy_files=False):
        '''
        fn = tex filename
        latex_string = (str) latex string to process (instead of reading from file)
        lib_dir = (str) path where python files (if any, e.g. for the general hint system) should be copied to and imported from
        '''
        self.fn = fn or ""
        self.verbose = verbose
        self.latex_string = latex_string
        self.add_wrap = add_wrap
        self.lib_dir = lib_dir
        self.extra_filters = extra_filters or []
        self.do_not_copy_files = do_not_copy_files	# used in testing
        self.filters = [ self.filter_fix_math,
                         self.filter_fix_section_headers,
                         self.filter_fix_solutions, 
                         self.filter_remmove_edxinclude, 
                         self.filter_fix_hint_definitions,
                         self.filter_fix_inline_prompts, 
                         self.process_includepy,
                         self.process_showhide,
                         self.pp_xml,			# next-to-next-to-last: pretty prints XML into string
                         self.filter_fix_question,	# must be next-to-last, because the result is not XML strict
                         self.add_explanations,
        ]
        self.filters += self.extra_filters
        self.explanations = {}				# csq_explanations are added at the end, after pretty printing, to preserve pp
        self.showhide_installed = False
        self.general_hint_system_installed = False	# if hints are used, the supporting python scripts must be in the library, and be imported

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

    def process_showhide(self, xhtml):
        xml = self.str2xml(xhtml)
        n = 0
        for sh in xml.findall(".//edxshowhide"):
            sh.tag = "div"
            shstr = etree.tostring(sh).decode("utf8")
            shkey = hashlib.sha224(shstr.encode("utf8")).hexdigest()[:20]
            shkey = "showhide_%s" % shkey
            sh.set("id", shkey)
            sh.set("style", "border: 2px solid;border-color:blue;border-radius:10px;padding-left:10px")
            script = etree.Element("script")
            script.set("type", "text/javascript")
            script.text = 'add_showhide_ws("%s");' % shkey
            sh.addprevious(script)
            n += 1
        if n:
            self.ensure_add_showhide(xml)
            if self.verbose:
                print("[latex2cs] processed %d <edxshowhide> stanzas" % n)
        return etree.tostring(xml).decode("utf8")

    def ensure_general_hint_system_installed(self):
        '''
        Ensure ghs code is installed
        '''
        if self.general_hint_system_installed:
            return
        preload_fn = "preload.py"
        syslib_dir = "%s/lib" % os.path.dirname(os.path.abspath(__file__))
        with open("%s/preload_code.py" % syslib_dir) as fp:
            preload_code = fp.read()

        userlib_cfn = "%s/calc.py" % self.lib_dir
        if not os.path.exists(userlib_cfn):
            if not self.do_not_copy_files:
                os.system("cp %s/calc.py %s" % (syslib_dir, userlib_cfn))
            print("[latex2cs] copied calc.py to %s" % userlib_cfn)

        userlib_gfn = "%s/general_hint_system.py" % self.lib_dir
        if not os.path.exists(userlib_gfn):
            if not self.do_not_copy_files:
                os.system("cp %s/general_hint_system.py %s" % (syslib_dir, userlib_gfn))
            print("[latex2cs] copied general_hint_system.py to %s" % userlib_gfn)

        preload_code = preload_code.format(calc=userlib_cfn, general_hint_system=userlib_gfn)
        preload = self.get_preload_py()
        if not preload_code in preload:
            with open(preload_fn, 'w') as prefp:
                prefp.write(preload_code)
            print("[latex2cs] Added code for calc and general_hint_system to preload.py")

        self.general_hint_system_installed = True

    def ensure_add_showhide(self, xml):
        '''
        Ensure showhide javascript is installed
        '''
        if self.showhide_installed:
            return
        doc = xml
        script = etree.Element("script")
        script.set("type", "text/javascript")
        script.set("src", "CURRENT/showhide.js")
        doc.insert(0, script)
        self.showhide_installed = True
        sdir = "__STATIC__"
        jsfn = "%s/lib/showhide.js" % os.path.dirname(os.path.abspath(__file__))
        sjsfn = "%s/%s" % (sdir, os.path.basename(jsfn))
        if not os.path.exists(sjsfn):
            if not self.do_not_copy_files:
                os.system("cp %s %s" % (jsfn, sjsfn))
            print("[latex2cs] Copied %s to %s" % (jsfn, sjsfn))


    def filter_fix_question(self, xhtml):
        '''
        change <question pythonic="1".*> to <question pythonic>
        xhtml should be a string
        '''
        xhtml = re.sub('<question pythonic="1".*?>', "<question pythonic>", xhtml)
        return xhtml

    def add_to_question(self, question, new_line, replacement_key=None):
        '''
        Add a new line to a <question> elment. 
        Handle this by transforming into string, adding, and transfomring back, so
        that elements in the string are not misorderd or otherwise mangled.

        question = etree element
        new_line = str
        replacement_key = (str) if provided, use this for the search and replace, instead of adding to end
        '''
        qstr = etree.tostring(question).decode("utf8")
        if replacement_key:
            qstr = qstr.replace(replacement_key, new_line)
        else:
            qstr = qstr.replace("</question>", "%s\n</question>" % new_line)
        new_q = etree.fromstring(qstr)
        question.addprevious(new_q)
        question.getparent().remove(question)
        
    def filter_remmove_edxinclude(self, xhtml):
        '''
        Remove <edxinclude>
        '''
        xml = self.str2xml(xhtml)
        n = 0
        for er in xml.findall(".//edxinclude"):
            er.getparent().remove(er)
            n += 1
        if self.verbose:
            print("[latex2cs] removed %d <edxinclude> lines" % n)
        return etree.tostring(xml).decode("utf8")

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
            print("[latex2cs] moved %s prompts to their following question" % nprompts)
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
            print("[latex2cs] moved %s solutions to their nearest question" % nmoved)
        return etree.tostring(xml).decode("utf8")

    def filter_fix_hint_definitions(self, xhtml):
        '''
        move <script> contents where hints are defined, into nearest pythonic question
        '''
        xml = self.str2xml(xhtml)
        nmoved = 0

        for problem in xml.findall(".//problem"):
            for script in problem.findall(".//script"):

                # script_xmlstr = self.pp_xml(script)
                script_code = script.text
                parent = script.getparent()
                parent.remove(script)

                cnt = 0
                while (parent.find(".//question") is None) and (cnt < 5) and (parent.find(".//problem") is None):
                    parent = parent.getparent()
                    cnt += 1

                moved = False
                for question in parent.findall(".//question"):
                    if question.get("has_script"):
                        continue
                    question.set("has_script", "1")

                    key = '# ===HINT-DEFINITION==='
                    self.add_to_question(question, script_code, key)

                    moved = True
                    nmoved += 1
                if not moved:
                    print("[latex2cs] Error!  Could not find question to move script into: %s" % script_code)

        if "===HINT-DEFINITION===" in xhtml:
            self.ensure_general_hint_system_installed()
            if self.verbose:
                print("[latex2cs] moved %s scripts to their nearest question" % nmoved)
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
        
    def get_preload_py(self):
        '''
        Read contents of preload.py and return.
        '''
        preload_fn = "preload.py"
        if os.path.exists(preload_fn):
            with open(preload_fn) as fp:
                preload = fp.read()
            return preload
        return ""

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
            preload = self.get_preload_py()
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


#-----------------------------------------------------------------------------

class VAction(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        curval = getattr(args, self.dest, 0) or 0
        values=values.count('v')+1
        setattr(args, self.dest, values + curval)

# -----------------------------------------------------------------------------

def CommandLine(args=None, arglist=None):
    '''
    Main command line.  Accepts args, to allow for simple unit testing.
    '''
    import pkg_resources  # part of setuptools

    version = pkg_resources.require("latex2cs")[0].version
    help_text = """usage: latex2cs [options] latex_file.tex

Version: {}

""".format(version)


    parser = argparse.ArgumentParser(description=help_text, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("texfile", help="tex file")
    parser.add_argument('-v', "--verbose", nargs=0, help="increase output verbosity (add more -v to increase versbosity)", action=VAction, dest='verbose')
    parser.add_argument("--lib-dir", help="library directory for python scripts", default=".")

    if not args:
        args = parser.parse_args(arglist)

    l2c = latex2cs(args.texfile, verbose=args.verbose, lib_dir=args.lib_dir)
    l2c.convert()


