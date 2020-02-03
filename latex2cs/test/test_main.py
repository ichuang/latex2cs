import os
from latex2cs.main import latex2cs

#-----------------------------------------------------------------------------
# unit tests

import unittest

class Test_latex2cs(unittest.TestCase):

    def test_main1(self):
        tex = r'''
\begin{edXtext}{OSR Problems}
{\LARGE The quantum operations formalism}

	The interaction of any quantum
	system with an environment can be mathematically expressed by
	a \href{http://en.wikipedia.org/wiki/Quantum_operation}{\em quantum operation}, ${\cal E}(\rho)$, defined as
	\be
		{\cal E}(\rho) = \sum_k E_k \rho E_k^\dagger
	\,,
	\ee
\end{edXtext}
        '''
        l2c = latex2cs(None, verbose=True, latex_string=tex, add_wrap=True, do_not_copy_files=True)
        xhtml = l2c.convert(ofn=None)
        print(xhtml)
        assert '''<html display_name="OSR Problems"''' in xhtml

    def test_question1(self):
        tex = r'''
\begin{edXproblem}{Operator Sum Representation: Projection}{url_name=s12-wk1-osr-ex1 attempts=10}
You are given a black box which takes single qubit
          states $\rho_{in}$ as input

\edXabox{type="custom" size=60 
  	prompts="$E_0 = $","$E_1 = $"
        answers="see solution","."
	expect="zdamp" 
        math="1"
        inline="1"
        cfn=check_osr2.catsoop_check_osr
}

\end{edXproblem}
        '''
        l2c = latex2cs("test.tex", verbose=True, latex_string=tex, add_wrap=True, do_not_copy_files=True)
        xhtml = l2c.convert(ofn=None)
        print(xhtml)

        expect = r'''<question pythonic>
csq_check_function = check_osr2.catsoop_check_osr
csq_inline = '1'
csq_soln = 'zdamp'
csq_options = {}
csq_npoints = 0
csq_output_mode = 'formatted'
csq_prompts = ["""<math>E_0 =</math>""", """<math>E_1 =</math>"""]
csq_solns = ["""see solution""", """."""]
csq_nsubmits = 10
</question>'''
        assert expect in xhtml

    def test_solution1(self):
        tex = r'''
\begin{edXproblem}{Operator Sum Representation: Projection}{url_name=s12-wk1-osr-ex1 attempts=10}
You are given a black box which takes single qubit
          states $\rho_{in}$ as input

\edXabox{type="custom" size=60 
  	prompts="$E_0 = $","$E_1 = $"
        answers="see solution","."
	expect="zdamp" 
        math="1"
        inline="1"
        cfn=check_osr2.catsoop_check_osr
}

\begin{edXsolution}
This is an explanation
\end{edXsolution}

\end{edXproblem}
        '''
        l2c = latex2cs("test.tex", verbose=True, latex_string=tex, add_wrap=True, do_not_copy_files=True)
        xhtml = l2c.convert(ofn=None)
        print(xhtml)

        expect = r'''<question pythonic>
csq_check_function = check_osr2.catsoop_check_osr
csq_inline = '1'
csq_soln = 'zdamp'
csq_options = {}
csq_npoints = 0
csq_output_mode = 'formatted'
csq_prompts = ["""<math>E_0 =</math>""", """<math>E_1 =</math>"""]
csq_solns = ["""see solution""", """."""]
csq_explanation=r"""
<solution>
  <span>This is an explanation </span>
</solution>
"""
csq_nsubmits = 10
</question>'''
        assert expect in xhtml


    def test_prompt1(self):
        tex = r'''
\begin{edXproblem}{Operator Sum Representation: Projection}{url_name=s12-wk1-osr-ex1 attempts=10}
You are given a black box which takes single qubit
          states $\rho_{in}$ as input

\edXinline{$g = $} 
\edXabox{type="custom" 
  size=30 
  expect="2*p-1" 
  cfn=check_osr2.catsoop_sympy_formula_check
  inline="1"
  math="1"
  hints="myhints"
}

\begin{edXsolution}
This is an explanation
\end{edXsolution}

\end{edXproblem}
        '''
        l2c = latex2cs("test.tex", verbose=True, latex_string=tex, add_wrap=True, do_not_copy_files=True)
        xhtml = l2c.convert(ofn=None)
        print(xhtml)

        expect = r'''<question pythonic>
csq_check_function = check_osr2.catsoop_sympy_formula_check
csq_inline = '1'
csq_soln = '2*p-1'
csq_options = {}
csq_npoints = 0
csq_output_mode = 'formatted'
csq_prompts = [""""""]
csq_solns = ["""2*p-1"""]
# HINT for: myhints
# ===HINT-DEFINITION===
hs = general_hint_system.HintSystem(hints=myhints)
csq_check_function = hs.catsoop_check_hint(csq_check_function)
csq_explanation=r"""
<solution>
  <span>This is an explanation </span>
</solution>
"""
csq_prompts = ["""<math>g =</math>"""]
csq_nsubmits = 10
</question>'''
        assert expect in xhtml

    def test_img1(self):
        mydir = os.path.dirname(os.path.abspath(__file__))
        imfn = "%s/test_data/image.png" % mydir
        tex = r'''
\begin{edXproblem}{Operator Sum Representation: Projection}{url_name=s12-wk1-osr-ex1 attempts=10}
You are given a black box which takes single qubit

\includegraphics[width=400]{%s}

\end{edXproblem}
        ''' % imfn
        l2c = latex2cs("test.tex", verbose=True, latex_string=tex, add_wrap=True, do_not_copy_files=True)
        xhtml = l2c.convert(ofn=None)
        print(xhtml)

        expect = r'''<img src="CURRENT/image.png" width="400"/>'''
        assert expect in xhtml

    def test_showhide1(self):
        tex = r'''
\begin{edXproblem}{Operator Sum Representation: Projection}{url_name=s12-wk1-osr-ex1 attempts=10}
You are given a black box which takes single qubit

\begin{edXshowhide}{Instructions for entering answer}
Please enter each operation element as a matrix, using nested lists delimited by square brackets. 
\end{edXshowhide}

test

\end{edXproblem}
        '''
        l2c = latex2cs("test.tex", verbose=True, latex_string=tex, add_wrap=True, do_not_copy_files=True)
        xhtml = l2c.convert(ofn=None)
        print(xhtml)

        expect = r'''<div description="Instructions for entering answer" id="showhide_2ee9cba29be94a952e3c"'''
        assert expect in xhtml

    def test_hint1(self):
        tex = r'''
\begin{edXproblem}{Operator Sum Representation: Projection}{url_name=s12-wk1-osr-ex1 attempts=10}
You are given a black box which takes single qubit


\begin{edXscript}

myhints = [ {'eval': "not string('*')", 'hint': 'Remember to explicitly indicate multiplication with *'},
            {'eval': "not symbol('p')", 'hint': "Shouldn't your answer depend on p?"},
          ]
  
\end{edXscript}

\edXinline{$g = $} 
\edXabox{type="custom" 
  size=30 
  expect="2*p-1" 
  cfn=catsoop_sympy_formula_check
  inline="1"
  math="1"
  hints="myhints"
}

Done

\end{edXproblem}
        '''
        l2c = latex2cs("test.tex", verbose=True, latex_string=tex, add_wrap=True, do_not_copy_files=True)
        xhtml = l2c.convert(ofn=None)
        print(xhtml)

        expect = r'''# HINT for: myhints


myhints = [ {'eval': "not string('*')", 'hint': 'Remember to explicitly indicate multiplication with *'},
            {'eval': "not symbol('p')", 'hint': "Shouldn't your answer depend on p?"},
          ]
  

hs = general_hint_system.HintSystem(hints=myhints)
csq_check_function = hs.catsoop_check_hint(csq_check_function)
'''
        assert expect in xhtml