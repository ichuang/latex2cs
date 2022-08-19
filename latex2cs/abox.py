'''
AnswerBox for catsoop output generation
'''

import re
import os
import sys
import hashlib
import traceback
from latex2edx.abox import split_args_with_quoted_strings

class AnswerBox:
    '''
    Convert latex specification of student-input answer box, into catsoop question code.
    '''
    CFN_MAP = {}
    DEFAULT_NPOINTS = 0

    def __init__(self, aboxstr, config=None, context=None, verbose=False):
        '''
        aboxstr = latex code
        config  = dict
        context = used for error reporting, and provides context like the line number and
                  filename where the abox is located.
        '''
        self.aboxstr = aboxstr
        self.verbose = verbose
        self.config = config or {}
        self.context = context
        self.xmlstr_just_code = aboxstr
        self.xmlstr = self.abox2xmlstr(aboxstr)

    def abox2xmlstr(self, aboxstr):
        '''
        Convert tex abox code into XML string for catsoop 
        '''
        if aboxstr.startswith('abox '): aboxstr = aboxstr[5:]
        s = aboxstr
        s = s.replace(' in_check= ', ' ')

        # unique ID for this abox, using hash
        try:
            aboxid = hashlib.sha1(aboxstr).hexdigest()[:10]
        except Exception as err:
            aboxid = hashlib.sha1(aboxstr.encode('utf8')).hexdigest()[:10]

        # parse answer box arguments into dict
        abargs = self.abox_args(s)
        self.abargs = abargs

        type2response = {'custom': 'pythonic',
                         'simple': 'pythonic',
                         'mapcfn': 'mapcfn',	# special for saving global mapping cfn from old_cfn
                         'external': None,
                         'code': None,
                         'oldmultichoice': None,
                         'multichoice': "multiplechoice",
                         'numerical': None,
                         'option': "dropdown",
                         'formula': None,
                         'shortans': "bigbox",
                         'shortanswer': None,
                         'string': None,
                         'symbolic': None,
                         'image': None,
                         'multicode': None,
                         'multiexternal': None,
                         'jsinput': None,
                         'config': 'config',	# special for setting default config parameters
        }

        if 'type' in abargs and abargs['type'] in type2response:
            abtype = type2response[abargs['type']]
        else:
            msg = "[latex2cs.abox] Error!  missing type declaration in abox: %s" % aboxstr
            raise Exception(msg)
        
        if abtype=="pythonic":
            xs = ['<question pythonic="1">']	# the ="1" is needed for XML format compliance; this is removed later in filter_fix_question
            #xs += ['<![CDATA[']
            xs += self.make_pythonic()
            #xs += ["]]>"]
            xs += ["</question>"]
            return "\n".join(xs)

        elif abtype=="multiplechoice":
            xs = ['<question multiplechoice="1">']
            xs += self.make_multiplechoice()
            xs += ["</question>"]
            return "\n".join(xs)

        elif abtype=="bigbox":
            xs = ['<question bigbox="1">']
            xs += self.make_bigbox()
            xs += ["</question>"]
            return "\n".join(xs)

        elif abtype=="dropdown":
            xs = ['<question multiplechoice="1">']
            xs += self.make_multiplechoice("dropdown")
            xs += ["</question>"]
            return "\n".join(xs)

        elif abtype is None:
            print("[latex2cs.abox] Warning!  Un-implemented abox type %s in %s" % (abargs['type'], aboxstr))
            return

        elif abtype=="mapcfn":
            try:
                ocfn = self.abargs.get("old_cfn")
                ncfn = self.abargs.get("cfn")
                AnswerBox.CFN_MAP[ocfn] = ncfn
            except Exception as err:
                raise Exception("[latex2cs.abox] error setting cfn map, abox:%s, err=%s, traceback=%s" % (aboxstr, err, traceback.format_exc()))
            print("[latex2cs.abox] mapping old cfn=%s to new cfn=%s" % (ocfn, ncfn))
            return

    def copy_attrib(self, xs, name, default=None, newname=None, skip_if_empty=False, filter_fun=None):
        '''
        Make csq_<name> = abargs[name] line in xs
        '''
        newname = newname or name
        val = self.abargs.get(name, default)
        if skip_if_empty and (val is None):
            return
        if filter_fun is not None:
            try:
                val = filter_fun(val)
            except Exception as err:
                raise Exception("[latex2cs.abox] cannot filter attribute %s by %s, err=%s, abox=%s" % (name, filter_fun, err, self.aboxstr))
        xs.append('csq_%s = %r' % (newname, val))

    def make_bigbox(self):
        '''
        Make a 'bigbox' answer box -- for open text response (ungraded)
        Return list of lines
        '''
        xs = []
        abargs = self.abargs

        # construct check function
        if 'cfn' in abargs:
            cfn = self.stripquotes(abargs['cfn'])
            if cfn in AnswerBox.CFN_MAP:
                ncfn = AnswerBox.CFN_MAP[cfn]
                if self.verbose:
                    print("[latex2cs.abox] mapping old cfn=%s -> %s in abox=%s" % (cfn, ncfn, self.aboxstr))
                cfn = ncfn

            xs.append("csq_check_function = %s" % cfn)
        else:
            xs.append("csq_check_function = lambda sub, soln: True")	# default - always correct

        self.copy_attrib(xs, 'npoints', AnswerBox.DEFAULT_NPOINTS)
        self.copy_attrib(xs, 'rows', None, "rows", skip_if_empty=True, filter_fun=int)
        self.copy_attrib(xs, 'cols', None, "cols", skip_if_empty=True, filter_fun=int)
        self.copy_attrib(xs, 'size', None, "size", skip_if_empty=True)

        if 'attempts' in abargs:
            try:
                nattempts = int(self.stripquotes(abargs['attempts']))
            except Exception as err:
                print("[latex2cs.abox] cannot parse attempts spec %s in %s, err=%s" % (abargs['attempts'], abargs, err))
                nattempts = None
            if nattempts is not None:
                xs.append("csq_nsubmits = %d" % nattempts)

        return xs

    def make_pythonic(self):
        '''
        Make a 'pythonic' answer box

        Return list of lines
        '''
        xs = []
        abargs = self.abargs
        self.require_args(['expect'])

        # construct check function
        if 'cfn' in abargs:
            cfn = self.stripquotes(abargs['cfn'])
            if cfn in AnswerBox.CFN_MAP:
                ncfn = AnswerBox.CFN_MAP[cfn]
                if self.verbose:
                    print("[latex2cs.abox] mapping old cfn=%s -> %s in abox=%s" % (cfn, ncfn, self.aboxstr))
                cfn = ncfn

            # special handling for options - add as named argument to cfn, if cfn starts with edx2catsoop.check
            if 'options' in abargs:
                options = abargs['options']
                if cfn.startswith("edx2catsoop.check"):
                    cfn1, cfn2 = cfn.rsplit(')', 1)
                    cfn = '%s,options="%s")%s' % (cfn1, options, cfn2)
                    print("[latex2cs.abox] merged options into cfn for %s" % cfn)
                else:
                    print("[latex2cs.abox] Warning!  options specified in abox=%s" % self.aboxstr)

            xs.append("csq_check_function = %s" % cfn)

        self.copy_attrib(xs, 'inline')
        self.copy_attrib(xs, 'expect', None, "soln")
        # self.copy_attrib(xs, 'options', {})
        self.copy_attrib(xs, 'npoints', AnswerBox.DEFAULT_NPOINTS)
        self.copy_attrib(xs, 'rows', None, "rows", skip_if_empty=True, filter_fun=int)
        self.copy_attrib(xs, 'cols', None, "cols", skip_if_empty=True, filter_fun=int)
        self.copy_attrib(xs, 'size', None, "size", skip_if_empty=True)
        xs.append("csq_output_mode = 'formatted'")

        if 'attempts' in abargs:
            try:
                nattempts = int(self.stripquotes(abargs['attempts']))
            except Exception as err:
                print("[latex2cs.abox] cannot parse attempts spec %s in %s, err=%s" % (abargs['attempts'], abargs, err))
                nattempts = None
            if nattempts is not None:
                xs.append("csq_nsubmits = %d" % nattempts)

        #if abxml.get('options', ''):
        #    abxml.set('cfn_extra_args', 'options')  # tells sandbox to include 'options' in cfn call arguments

        if 'answers' not in abargs:
            answers = [self.stripquotes(abargs['expect'])]
        else:   # multiple inputs for this customresponse
            ansstr, answers = self.get_options(abargs, 'answers')
        orig_answers = answers[:]	# copy of answers (answers may be changed, if wrapped)
        if 'prompts' in abargs:
            promptstr, prompts = self.get_options(abargs, 'prompts')
        else:
            prompts = ['']
        if not len(prompts) == len(answers):
            msg = "Error: number of answers and prompts must match in:"
            msg += aboxstr
            msg += "\nabox located: %s\n" % self.context
            raise Exception(msg)
        
        xs.append("csq_prompts = [%s]" % ", ".join([ self.quoteit(x) for x in prompts ]))
        xs.append("csq_solns = [%s]" % ", ".join([ self.quoteit(x) for x in answers ]))

        if 'hints' in abargs:
            hname = self.stripquotes(abargs['hints'])
            xs.append("# HINT for: %s" % hname)
            xs.append("# ===HINT-DEFINITION===")
            xs.append("hs = general_hint_system.HintSystem(hints=%s)" % hname)
            xs.append("csq_check_function = hs.catsoop_check_hint(csq_check_function)")

        return xs

    def make_multiplechoice(self, renderer="checkbox"):
        '''
        Make a 'multiplechoice' answer box
        '''
        xs = []
        abargs = self.abargs
        self.require_args(['expect'])
        self.copy_attrib(xs, 'npoints', AnswerBox.DEFAULT_NPOINTS)
        # self.copy_attrib(xs, 'npoints', 0)
        self.copy_attrib(xs, 'prompt', '')
        self.copy_attrib(xs, 'renderer', renderer)

        optionstr, options = self.get_options(abargs)
        xs.append("csq_options = [%s]" % ", ".join([ self.quoteit(x) for x in options ]))

        # expect = self.stripquotes(abargs['expect'])
        expectstr, expect = self.get_options(abargs, 'expect')	# allow for expect to be a list of quoted strings
        if renderer=="checkbox":
            soln = [(x in expect) for x in options]
            xs.append("csq_soln = [%s]" % ", ".join(map(str, soln)))
        else:
            xs.append('csq_soln = r"""%s"""' % expect[0])

        if 'attempts' in abargs:
            try:
                nattempts = int(self.stripquotes(abargs['attempts']))
            except Exception as err:
                print("[latex2cs.abox] cannot parse attempts spec %s in %s, err=%s" % (abargs['attempts'], abargs, err))
                nattempts = None
            if nattempts is not None:
                xs.append("csq_nsubmits = %d" % nattempts)
        return xs


    def quoteit(self, x):
        return 'r"""%s"""' % x

    def get_options(self, abargs, arg='options'):
        optstr = abargs[arg]			# should be double quoted strings, comma delimited
        # EVH 01-22-2015: Inserting quotes around single option for proper
        # parsing of choices containing commas
        if not optstr.startswith('"') and not optstr.startswith("'"):
            optraw = repr(optstr)
            optstr = optraw[0] + optstr + optraw[0]
        options = split_args_with_quoted_strings(optstr, lambda x: x == ',')		# turn into list of strings
        options = list(map(self.stripquotes, options))
        options = [x.strip() for x in options]		# strip strings
        if "" in options: options.remove("")
        optionstr = ','.join([r"'%s'" % x for x in options])  # string of single quoted strings
        optionstr = "(%s)" % optionstr				# enclose in parens
        return optionstr, options
            
    def require_args(self, argnames):
        for argname in argnames:
            if argname not in self.abargs:
                msg = "============================================================\n"
                msg += "Error - abox requires %s argument\n" % argname
                msg += "Answer box string is \"%s\"\n" % self.aboxstr
                msg += "abox located: %s\n" % self.context
                # raise Exception, "Bad abox"
                raise Exception(msg)
                # sys.exit(-1)

    def abox_args(self, s):
        '''
        Parse arguments of abox.  Splits by space delimitation.

        Test-spec argument keys are handled specially: test_*=...
        Arguments with those keys are stored in self.tests ; they may be used
        by the caller to construct answer box unit tests and course unit tests.
        '''
        s = s.replace('\u2019', "'")
        try:
            s = str(s)
        except Exception as err:
            print("Error %s in obtaining string form of abox argument %s" % (err, s))
            return {}
        try:
            # abargstxt = shlex.split(s)
            abargstxt = split_args_with_quoted_strings(s)
        except Exception as err:
            print("Error %s in parsing abox argument %s" % (err, s))
            return {}

        if '' in abargstxt:
            abargstxt.remove('')

        abargs = {}
        try:
            for key, val in [x.split('=', 1) for x in abargstxt]:
                if key.startswith("test_"):
                    self.process_test_arg(key, val)
                else:
                    abargs[key] = val
        except Exception as err:
            print("Error %s" % err)
            print("Failed in parsing args = %s" % s)
            print("abargstxt = %s" % abargstxt)
            raise

        for arg in abargs:
            abargs[arg] = self.stripquotes(abargs[arg], checkinternal=True)

        return abargs

    def stripquotes(self, x, checkinternal=False):
        if x.startswith('"') and x.endswith('"'):
            if checkinternal and '"' in x[1:-1]:
                return x
            return x[1:-1]
        if x.startswith("'") and x.endswith("'"):
            return x[1:-1]
        return x
            
