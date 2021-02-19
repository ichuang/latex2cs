#!/usr/bin/env python

import os
import re
import sys
import codecs
import hashlib
import argparse
import subprocess
from path import Path as path
from lxml import etree
from latex2edx.plastexit import plastex2xhtml

from .abox import AnswerBox
from .abox import split_args_with_quoted_strings

# -----------------------------------------------------------------------------

class latex2cs:
    def __init__(self, fn, latex_string=None, verbose=False, extra_filters=None, add_wrap=False, lib_dir=".",
                 do_not_copy_files=False, default_npoints=1):
        '''
        fn = tex filename
        latex_string = (str) latex string to process (instead of reading from file)
        lib_dir = (str) path where python files (if any, e.g. for the general hint system) should be copied to and imported from
        default_npoints = (int) number of points to set csq_npoints to, if otherwise unspecified
        '''
        self.fn = fn or ""
        self.verbose = verbose
        self.latex_string = latex_string
        self.add_wrap = add_wrap
        self.lib_dir = lib_dir
        self.output_dir = path(".")				# todo: make this configurable
        self.default_npoints = default_npoints
        self.extra_filters = extra_filters or []
        self.do_not_copy_files = do_not_copy_files	# used in testing
        self.filters = [ self.filter_fix_math,
                         self.filter_fix_math_eqnarray,
                         self.fix_attrib_string,
                         self.filter_fix_section_headers,
                         self.process_dndtex,		# needs unit test
                         self.filter_fix_solutions, 
                         self.filter_remmove_edxinclude, 
                         self.filter_fix_hint_definitions,
                         self.filter_fix_inline_prompts, 
                         self.filter_fix_question_names, 
                         self.filter_fix_nsubmits, 
                         self.filter_fix_ref, 
                         self.process_edxxml,		# needs unit test
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
        self.question_names = []			# used to make sure all question names are globally unique

    def convert(self, ofn=None, skip_output=False):
        imdir = "__STATIC__"
        imurl = ""
        imurl_fmt = "CURRENT/{fnbase}"
        ofn = ofn or self.fn.replace(".tex", ".md")
        if not os.path.exists(imdir):
            os.mkdir(imdir)
        AnswerBox.DEFAULT_NPOINTS = self.default_npoints
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

        if skip_output:
            return xhtml

        if ofn:
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
                if self.verbose > 2:
                    print("[latex2cs] ran tostring on xml, producing type %s" % type(xml))
            # print("xml has type %s" % type(xml))
            p.stdin.write(xml)
            p.stdin.close()
            p.wait()
            with codecs.open('tmp.xml', encoding="utf8") as xfp:
                xml = xfp.read()
            xml = xml.encode("utf8")
        except Exception as err:
            print("[xbundle.py] Warning - no xmllint")
            print(err)
            xml = etree.tostring(xml, pretty_print=True)

        xml = xml.decode("utf8")
        if xml.startswith('<?xml '):
            xml = xml.split('\n', 1)[1]
        return xml

    @staticmethod
    def remove_parent_p(xml):
        '''
        If xml is inside an otherwise empty <p>, then push it up and remove the <p>
        '''
        p = xml.getparent()
        todrop = xml
        where2add = xml
        if p.tag == 'p' and not p.text.strip() and len(p) == 1:	 # if in empty <p> then remove that <p>
            todrop = p
            where2add = p
            p = p.getparent()

        # move from xml to parent: text, children, and tail
        if xml.text:
            if xml.getprevious() is not None:
                if xml.getprevious().tail:
                    xml.getprevious().tail += xml.text
                else:
                    xml.getprevious().tail = xml.text
            else:
                if p.text:
                    p.text += xml.text
                else:
                    p.text = xml.text
        for child in xml:
            where2add.addprevious(child)
        if xml.tail:
            if 'child' in locals():
                if child.tail:
                    child.tail += xml.tail
                else:
                    child.tail = xml.tail
            else:
                if p.text:
                    p.text += xml.tail
                else:
                    p.text = xml.tail
        p.remove(todrop)

    def process_edxxml(self, xhtml):
        '''
        move content of edXxml into body
        If edXxml is within a <p> then drop the <p>.  This allows edXxml to be used for discussion and video.
        '''
        xml = self.str2xml(xhtml)
        for edxxml in xml.findall('.//edxxml'):
            self.remove_parent_p(edxxml)
        return etree.tostring(xml).decode("utf8")

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
                preload += preload_code
                prefp.write(preload)
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
        xhtml = re.sub('<question (pythonic|multiplechoice|drag_and_drop)="1".*?>', r"<question \1>", xhtml)
        return xhtml

    def add_to_question(self, question, new_line, replacement_key=None, at_front=False):
        '''
        Add a new line to a <question> elment. 
        Handle this by transforming into string, adding, and transfomring back, so
        that elements in the string are not misorderd or otherwise mangled.

        question = etree element
        new_line = str
        replacement_key = (str) if provided, use this for the search and replace, instead of adding to end
        at_front = (bool) if true, adds new content immediately after <question ...>; default False
        '''
        qstr = etree.tostring(question).decode("utf8")
        if replacement_key:
            new_qstr = qstr.replace(replacement_key, new_line)
        else:
            if at_front:
                new_qstr = re.sub("(<question [^>]+?>)", "\\1\n%s\n" % new_line, qstr)
            else:
                new_qstr = qstr.replace("</question>", "%s\n</question>" % new_line)
        if new_qstr == qstr:
            return False
        try:
            new_q = etree.fromstring(new_qstr)
        except Exception as err:
            print("[latex2cs] failed to add to question, new_qstr=%s" % new_qstr)
            raise
        question.addprevious(new_q)
        question.getparent().remove(question)
        return True
        
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
        
    def filter_fix_math_eqnarray(self, xhtml):
        '''
        Math eqnarray is turned into a table, but the width of the left-algined column is abnormally small.
        Fix this by making it wider.
        '''
        xml = self.str2xml(xhtml)
        n = 0
        for er in xml.findall('.//table[@class="eqnarray"]'):
            for ma in er.findall('.//td'):
                mas = ma.get("style")
                if ("text-align:left" in mas) and ("vertical-align:middle" in mas):
                    n += 1
                    ma.set("style", mas + ";width:60%")
        if self.verbose:
            print("[latex2cs] extended width of %d <td> lines in eqnarray tables" % n)
        return etree.tostring(xml).decode("utf8")

    def filter_fix_ref(self, xhtml):
        '''
        change <ref> to <b> (this is used by equation references, for example; catsoop looks for anchors with labels, so it crashes on these, otherwise)
        '''
        xml = self.str2xml(xhtml)
        for ref in xml.findall(".//ref"):
            ref.tag = "b"
        return etree.tostring(xml).decode("utf8")

    def filter_fix_inline_prompts(self, xhtml):
        '''
        Move inline prompts into question as csq_prompt or csq_prompts
        '''
        xml = self.str2xml(xhtml)
        nprompts = 0
        for question in xml.findall(".//question"):
            prev = question.getprevious()
            if prev is None and question.getparent().tag=="p":
                prev = question.getparent().getprevious()
            if prev is not None and prev.tag=="p" and not prev.get("style")=="display:inline":
                if len(prev) and prev[0].tag=="p" and prev[0].get("style")=="display:inline":
                    prev = prev[0]
            if prev is not None and prev.tag=="p" and prev.get("style")=="display:inline":
                prompt = etree.tostring(prev).decode("utf8")
                prompt = prompt.split(">", 1)[1].rsplit("</", 1)[0]	# remove <p> and </p>
                prev.getparent().remove(prev)
                if question.get("multiplechoice"):
                    new_line = 'csq_prompt = r"""%s"""' % (prompt)
                else:
                    new_line = 'csq_prompts = [r"""%s"""]' % (prompt)
                self.add_to_question(question, new_line)
                nprompts += 1
            elif prev is not None and prev.get("style")=="display:inline":
                print("question %s, prev=%s" % (question, etree.tostring(prev)))

        if self.verbose:
            print("[latex2cs] moved %s prompts to their following question" % nprompts)
        return etree.tostring(xml).decode("utf8")

    @staticmethod
    def do_attrib_string(elem):
        '''
        parse attribute strings, and add to xml elements.
        attribute strings are space delimited, and optional for elements
        like chapter, sequential, vertical, text
        '''
        attrib_string = elem.get('attrib_string', '')
        if attrib_string:
            attrib_list = split_args_with_quoted_strings(attrib_string)
            if len(attrib_list) == 1 & len(attrib_list[0].split('=')) == 1:  # a single number n is interpreted as weight="n"
                elem.set('weight', attrib_list[0])
            else:  # the normal case, can remove backwards compatibility later if desired
                for s in attrib_list:
                    attrib_and_val = s.split('=')
                    if len(attrib_and_val) != 2:
                        print("ERROR! the attribute list '%s' for element %s is not properly formatted" % (attrib_string, elem.tag))
                        # print "attrib_and_val=%s" % attrib_and_val
                        print(etree.tostring(elem))
                        sys.exit(-1)
                    elem.set(attrib_and_val[0], attrib_and_val[1].strip("\""))  # remove extra quotes
        if 'attrib_string' in list(elem.keys()):
            elem.attrib.pop('attrib_string')  # remove attrib_string

    def fix_attrib_string(self, xmlstr):
        '''
        Convert attrib_string in <problem>, <chapter>, etc. to attributes, intelligently.
        '''
        TAGS = ['problem', 'chapter', 'sequential', 'vertical', 'course', 'html', 'video', 'discussion', 'edxdndtex',
                'conditional', 'lti', 'split_test']
        xml = self.str2xml(xmlstr)
        for tag in TAGS:
            for elem in xml.findall('.//%s' % tag):
                self.do_attrib_string(elem)
        return etree.tostring(xml).decode("utf8")


    def filter_fix_nsubmits(self, xhtml):
        '''
        If max number of attempts (csq_nsubmits) is not specified, then inherit it from the enclosing <problem>
        '''
        xml = self.str2xml(xhtml)
        n = 0
        for question in xml.findall(".//question"):
            if "csq_nsubmits" in etree.tostring(question).decode("utf8"):
                continue
            parent = question.getparent()
            cnt = 0
            while parent and (not parent.tag=="problem") and cnt < 10:
                parent = parent.getparent()
                cnt += 1
            problem = parent
            if not parent:
                print("[latex2cs] warning - question %s not within a <problem>" % question)
                continue
            attempts = problem.get("attempts")
            if not attempts:
                print("[latex2cs] warning - problem has no max attempts specified: %s" % problem)
                continue
            try:
                attempts = int(attempts)
            except Exception as err:
                print("[latex2cs] cannot parse attempts=%s for problem %s" % (attempts, problem))
                continue
            new_line = "csq_nsubmits = %s" % attempts
            self.add_to_question(question, new_line)
            n += 1
        
        if n and self.verbose:
            print("[latex2cs] fixed %d questions to have csq_nsubmits defined" % n)
        return etree.tostring(xml).decode("utf8")


    def make_valid_question_name(self, name):
        '''
        catsoop only allows question names matching this:

        _valid_qname = re.compile(r"^[A-Za-z][_A-Za-z0-9]*$")

        which is different from edX's url_name criterion, which allows dashes, for example.
        Transform the question name untill acceptable, and return.
        '''
        valid_qname = re.compile(r"^[A-Za-z][_A-Za-z0-9]*$")
        if valid_qname.match(name):
            return name
        name = name.replace("-", "_")
        if valid_qname.match(name):
            return name
        raise Exception("[latex2cs] failed to generate valid csq_name from edX url_name=%s" % name)


    def filter_fix_question_names(self, xhtml):
        '''
        If url_name is specified for a given problem, then use that to generate csq_name for any questions inside the problem
        '''
        xml = self.str2xml(xhtml)
        n = 0
        nq = 0
        for problem in xml.findall(".//problem"):
            url_name = problem.get("url_name")
            if not url_name:
                continue
            url_name = self.make_valid_question_name(url_name)
            qcnt = 0
            for question in problem.findall(".//question"):
                if "csq_name" in etree.tostring(question).decode("utf8"):
                    continue
                qcnt += 1
                csq_name = "%s_%02d" % (url_name, qcnt)
                if csq_name in self.question_names:
                    print("[latex2cs] Warning: question name %s already exists, but trying to add again at %s?" % (csq_name, problem))
                    while csq_name in self.question_names:
                        csq_name += "x"
                self.question_names.append(csq_name)
                new_line = "csq_name = '%s'" % csq_name
                self.add_to_question(question, new_line)
            n += 1
            nq += qcnt
        
        if n:
            print("[latex2cs] fixed %d problems (%s questions total) to have csq_name defined" % (n, nq))
        return etree.tostring(xml).decode("utf8")


    def filter_fix_solutions(self, xhtml):
        '''
        move <solution>...</solution> into nearest csq_explanation inside <question>
        '''
        xml = self.str2xml(xhtml)
        nmoved = 0

        for problem in xml.findall(".//problem"):
            for solution in problem.findall(".//solution"):

                bhead = solution.xpath('.//b[text()="Solution:"]')      # remove <b>Solution:</b> and is containing <p>, if present
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
                    replaced = self.add_to_question(question, script_code, key)	# first try placing at HINT position (see abox.py)
                    if not replaced:
                        replaced = self.add_to_question(question, script_code, at_front=True)  # else just place at end before </question>
                        if not replaced:
                            print("['atex2cs] Error! Could not move script to proper position within question, script=%s" % script_code)

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


    def process_dndtex(self, xmlstr):
        '''
        Handle \edXdndtex{dnd_file.tex} inclusion of latex2dnd tex inputs.
        The file may also be a dnd_file.dndspec
        '''
        xml = self.str2xml(xmlstr)
        tag = './/edxdndtex'
        for dndxml in xml.findall(tag):
            dndfn = dndxml.text
            linenum = dndxml.get('linenum', '<unavailable>')
            texfn = dndxml.get('filename', '<unavailable>')
            check_fn = dndxml.get('cfn')
            print("[latex2cs.process_dndtex] dndfn=%s, check_fn=%s" % (dndfn, check_fn))
            if dndfn is None:
                print("Error: %s must specify dnd tex filename!" % tag)  # EVH changed 'cmd' to 'tag'
                print("See tex file %s line %s" % (texfn, linenum))
                raise
            dndfn = dndfn.strip()
            if not (dndfn.endswith('.tex') or dndfn.endswith('.dndspec')):
                print("Error: dnd file %s should be a .tex or a .dndspec file!" % dndfn)
                print("See tex file %s line %s" % (texfn, linenum))
                raise
            if not os.path.exists(dndfn):
                print("Error: dnd tex file %s does not exist!" % dndfn)
                print("See tex file %s line %s" % (texfn, linenum))
                raise
            try:
                with open(dndfn) as dfp:
                    dndsrc = dfp.read()
            except Exception as err:
                print("Error %s: cannot open dnd tex / dndpec file %s to read" % (err, dndfn))
                print("See tex file %s line %s" % (texfn, linenum))
                raise

            # Use latex2dnd to compile dnd tex into edX XML.
            #
            # For dndfile.tex, at least two files must be produced: dndfile_dnd.xml and
            # dndfile_dnd.png
            #
            # we copy all the *.png files to static/images/<dndfile>/
            #
            # run latex2dnd only when the dndfile_dnd.xml file is older than dndfile.tex

            fnb = os.path.basename(dndfn)
            fnpre = fnb.rsplit('.', 1)[0]
            fndir = path(os.path.dirname(dndfn))
            xmlfn = fndir / (fnpre + '_dnd.xml')

            run_latex2dnd = False
            if not os.path.exists(xmlfn):
                run_latex2dnd = True
            if not run_latex2dnd:
                dndmt = os.path.getmtime(dndfn)
                xmlmt = os.path.getmtime(xmlfn)
                if dndmt > xmlmt:
                    run_latex2dnd = True
            if run_latex2dnd:
                options = ''
                if dndxml.get('can_reuse', 'False').lower().strip() != 'false':
                    options += '-C'
                cmd = 'cd "%s"; latex2dnd --cleanup -r %s -v %s %s' % (fndir, dndxml.get('resolution', 210), options, fnb)
                print("--> Running %s" % cmd)
                sys.stdout.flush()
                status = os.system(cmd)
                if status:
                    print("Oops - latex2dnd apparently failed - aborting!")
                    raise Exception("Oops - latex2dnd apparently failed - aborting!")
                imdir = self.output_dir / ('__STATIC__/images/%s' % fnpre)
                if not os.path.exists(imdir):
                    os.system('mkdir -p %s' % imdir)
                cmd = "cp %s/%s*.png %s/" % (fndir, fnpre, imdir)
                print("----> Copying dnd images: %s" % cmd)
                sys.stdout.flush()
                status = os.system(cmd)
                if status:
                    print("Oops - copying images from latex2dnd apparently failed - aborting!")
                    raise Exception("Oops - latex2dnd apparently failed - aborting!")
            else:
                print("--> latex2dnd XML file %s is up to date: %s" % (xmlfn, fnpre))

            # change dndtex tag to become <question drag_and_drop=1>
            # Process <dndfile>_dnd.xml and create assignments

            dndxml.tag = 'question'
            for k in dndxml.attrib.keys():	# remove old attributes
                dndxml.attrib.pop(k)
            dndxml.set("drag_and_drop", "1")
            dndxml.text = self.make_drag_and_drop(xmlfn, check_fn)

        return etree.tostring(xml).decode("utf8")

    def make_drag_and_drop(self, xmlfn, check_fn=None):
        '''
        Make catsoop question content for drag-and-drop problem, based on XML output of latex2dnd
        xmlfn = dnd XML filename
        checn_fn = check function name (if provided)
        '''
        text = [""]
        print("Procesing drag-and-drop problem from %s" % xmlfn)
        xml = etree.parse(xmlfn).getroot()
        dnd_xml = etree.tostring(xml.find(".//drag_and_drop_input")).decode("utf8")
        answer = xml.find(".//answer")

        if check_fn is not None:
            cfn = check_fn
            print("[latex2cs.make_drag_and_drop] cfn=%s" % cfn)
            text.append('csq_check_function = %s' % cfn)

        elif answer is None:
            script = xml.find(".//script")
            cfn = script.text
            cfn += "\n"
            cfn += "ret = dnd_check_function(None, submission[0])\n"
            cfn += "correct = ['incorrect']\n"
            cfn += "if ret.get('ok'): correct = ['correct']\n"
            cfn += "if 'msg' in ret:\n"
            cfn += "    messages = ret.get('msg')\n"

            # overload old formula equality testing with new sympy formula check
            if 'def is_formula_equal' in cfn:
                txt = "def is_formula_equal(expected, given, samples):\n"
                txt += "    ret = sympy_check.sympy_formula_check(expected, given)\n"
                txt += "    return ret['ok']\n\n"
                txt += "def old_is_formula_equal"
                cfn = cfn.replace("def is_formula_equal", txt)

            text.append('csq_check_function = r"""%s"""' % cfn)

        else:
            cfn = answer.text
            text.append('csq_check_function = r"""%s"""' % cfn)

        sol = xml.find(".//solution")
        sol.tag = "span"
        sol = etree.tostring(sol).decode("utf8")
        sol = sol.replace('"/static/', '"CURRENT/')
        
        text.append('csq_soln = r"""%s"""' % sol)
        text.append('csq_dnd_xml = r"""%s"""' % dnd_xml)
        text.append("")			# ensure empty line at end
        return '\n'.join(text)

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
    parser.add_argument("-o", "--output", help="output filename", default="")
    parser.add_argument("--add-wrap", help="add begin{document}...end{document} wrapper around tex", action="store_true")

    if not args:
        args = parser.parse_args(arglist)

    l2c = latex2cs(args.texfile, verbose=args.verbose, lib_dir=args.lib_dir, add_wrap=args.add_wrap)
    l2c.convert(ofn=args.output)


