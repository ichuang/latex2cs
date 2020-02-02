"""
Parser and evaluator for FormulaResponse and NumericalResponse

Uses pyparsing to parse. Main function as of now is evaluator().
"""

import math
import operator
import numbers
import numpy
import scipy.constants

from pyparsing import (
    Word, Literal, CaselessLiteral, ZeroOrMore, MatchFirst, Optional, Forward,
    Group, ParseResults, stringEnd, Suppress, Combine, alphas, nums, alphanums
)
from functools import reduce


#-----------------------------------------------------------------------------

class functions:
    """
    Provide the mathematical functions that numpy doesn't.
    
    Specifically, the secant/cosecant/cotangents and their inverses and
    hyperbolic counterparts
    """
    
    # Normal Trig
    @staticmethod
    def sec(arg):
        """
        Secant
        """
        return 1 / numpy.cos(arg)
    
    
    @staticmethod
    def csc(arg):
        """
        Cosecant
        """
        return 1 / numpy.sin(arg)
    
    
    @staticmethod
    def cot(arg):
        """
        Cotangent
        """
        return 1 / numpy.tan(arg)
    
    
    # Inverse Trig
    # http://en.wikipedia.org/wiki/Inverse_trigonometric_functions#Relationships_among_the_inverse_trigonometric_functions
    @staticmethod
    def arcsec(val):
        """
        Inverse secant
        """
        return numpy.arccos(1. / val)
    
    
    @staticmethod
    def arccsc(val):
        """
        Inverse cosecant
        """
        return numpy.arcsin(1. / val)
    
    
    @staticmethod
    def arccot(val):
        """
        Inverse cotangent
        """
        if numpy.real(val) < 0:
            return -numpy.pi / 2 - numpy.arctan(val)
        else:
            return numpy.pi / 2 - numpy.arctan(val)
    
    
    # Hyperbolic Trig
    @staticmethod
    def sech(arg):
        """
        Hyperbolic secant
        """
        return 1 / numpy.cosh(arg)
    
    
    @staticmethod
    def csch(arg):
        """
        Hyperbolic cosecant
        """
        return 1 / numpy.sinh(arg)
    
    
    @staticmethod
    def coth(arg):
        """
        Hyperbolic cotangent
        """
        return 1 / numpy.tanh(arg)
    
    
    # And their inverses
    @staticmethod
    def arcsech(val):
        """
        Inverse hyperbolic secant
        """
        return numpy.arccosh(1. / val)
    
    
    @staticmethod
    def arccsch(val):
        """
        Inverse hyperbolic cosecant
        """
        return numpy.arcsinh(1. / val)
    
    
    @staticmethod
    def arccoth(val):
        """
        Inverse hyperbolic cotangent
        """
        return numpy.arctanh(1. / val)

#-----------------------------------------------------------------------------

DEFAULT_FUNCTIONS = {
    'sin': numpy.sin,
    'cos': numpy.cos,
    'tan': numpy.tan,
    'sec': functions.sec,
    'csc': functions.csc,
    'cot': functions.cot,
    'sqrt': numpy.sqrt,
    'log10': numpy.log10,
    'log2': numpy.log2,
    'ln': numpy.log,
    'exp': numpy.exp,
    'arccos': numpy.arccos,
    'arcsin': numpy.arcsin,
    'arctan': numpy.arctan,
    'arcsec': functions.arcsec,
    'arccsc': functions.arccsc,
    'arccot': functions.arccot,
    'abs': numpy.abs,
    'fact': math.factorial,
    'factorial': math.factorial,
    'sinh': numpy.sinh,
    'cosh': numpy.cosh,
    'tanh': numpy.tanh,
    'sech': functions.sech,
    'csch': functions.csch,
    'coth': functions.coth,
    'arcsinh': numpy.arcsinh,
    'arccosh': numpy.arccosh,
    'arctanh': numpy.arctanh,
    'arcsech': functions.arcsech,
    'arccsch': functions.arccsch,
    'arccoth': functions.arccoth
}
DEFAULT_VARIABLES = {
    'i': numpy.complex(0, 1),
    'j': numpy.complex(0, 1),
    'e': numpy.e,
    'pi': numpy.pi,
    'k': scipy.constants.k,  # Boltzmann: 1.3806488e-23 (Joules/Kelvin)
    'c': scipy.constants.c,  # Light Speed: 2.998e8 (m/s)
    'T': 298.15,  # Typical room temperature: 298.15 (Kelvin), same as 25C/77F
    'q': scipy.constants.e  # Fund. Charge: 1.602176565e-19 (Coulombs)
}

# We eliminated the following extreme suffixes:
#   P (1e15), E (1e18), Z (1e21), Y (1e24),
#   f (1e-15), a (1e-18), z (1e-21), y (1e-24)
# since they're rarely used, and potentially confusing.
# They may also conflict with variables if we ever allow e.g.
#   5R instead of 5*R
SUFFIXES = {
    '%': 0.01, 'k': 1e3, 'M': 1e6, 'G': 1e9, 'T': 1e12,
    'c': 1e-2, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12
}


class UndefinedVariable(Exception):
    """
    Indicate when a student inputs a variable which was not expected.
    """
    pass


def lower_dict(input_dict):
    """
    Convert all keys in a dictionary to lowercase; keep their original values.

    Keep in mind that it is possible (but not useful?) to define different
    variables that have the same lowercase representation. It would be hard to
    tell which is used in the final dict and which isn't.
    """
    return {k.lower(): v for k, v in input_dict.items()}


# The following few functions define evaluation actions, which are run on lists
# of results from each parse component. They convert the strings and (previously
# calculated) numbers into the number that component represents.

def super_float(text):
    """
    Like float, but with SI extensions. 1k goes to 1000.
    """
    if text[-1] in SUFFIXES:
        return float(text[:-1]) * SUFFIXES[text[-1]]
    else:
        return float(text)


def eval_number(parse_result):
    """
    Create a float out of its string parts.

    e.g. [ '7.13', 'e', '3' ] ->  7130
    Calls super_float above.
    """
    return super_float("".join(parse_result))


def eval_atom(parse_result):
    """
    Return the value wrapped by the atom.

    In the case of parenthesis, ignore them.
    """
    # Find first number in the list
    result = next(k for k in parse_result if isinstance(k, numbers.Number))
    return result


def eval_power(parse_result):
    """
    Take a list of numbers and exponentiate them, right to left.

    e.g. [ 2, 3, 2 ] -> 2^3^2 = 2^(3^2) -> 512
    (not to be interpreted (2^3)^2 = 64)
    """
    # `reduce` will go from left to right; reverse the list.
    parse_result = reversed(
        [k for k in parse_result
         if isinstance(k, numbers.Number)]  # Ignore the '^' marks.
    )
    # Having reversed it, raise `b` to the power of `a`.
    power = reduce(lambda a, b: b ** a, parse_result)
    return power


def eval_parallel(parse_result):
    """
    Compute numbers according to the parallel resistors operator.

    BTW it is commutative. Its formula is given by
      out = 1 / (1/in1 + 1/in2 + ...)
    e.g. [ 1, 2 ] -> 2/3

    Return NaN if there is a zero among the inputs.
    """
    if len(parse_result) == 1:
        return parse_result[0]
    if 0 in parse_result:
        return float('nan')
    reciprocals = [1. / e for e in parse_result
                   if isinstance(e, numbers.Number)]
    return 1. / sum(reciprocals)


def eval_sum(parse_result):
    """
    Add the inputs, keeping in mind their sign.

    [ 1, '+', 2, '-', 3 ] -> 0

    Allow a leading + or -.
    """
    total = 0.0
    current_op = operator.add
    for token in parse_result:
        if token == '+':
            current_op = operator.add
        elif token == '-':
            current_op = operator.sub
        else:
            total = current_op(total, token)
    return total


def eval_product(parse_result):
    """
    Multiply the inputs.

    [ 1, '*', 2, '/', 3 ] -> 0.66
    """
    prod = 1.0
    current_op = operator.mul
    for token in parse_result:
        if token == '*':
            current_op = operator.mul
        elif token == '/':
            current_op = operator.truediv
        else:
            prod = current_op(prod, token)
    return prod


def add_defaults(variables, functions, case_sensitive):
    """
    Create dictionaries with both the default and user-defined variables.
    """
    all_variables = dict(DEFAULT_VARIABLES)
    all_functions = dict(DEFAULT_FUNCTIONS)
    all_variables.update(variables)
    all_functions.update(functions)

    if not case_sensitive:
        all_variables = lower_dict(all_variables)
        all_functions = lower_dict(all_functions)

    return (all_variables, all_functions)


def evaluator(variables, functions, math_expr, case_sensitive=False):
    """
    Evaluate an expression; that is, take a string of math and return a float.

    -Variables are passed as a dictionary from string to value. They must be
     python numbers.
    -Unary functions are passed as a dictionary from string to function.
    """
    # No need to go further.
    if math_expr.strip() == "":
        return float('nan')

    # Parse the tree.
    math_interpreter = ParseAugmenter(math_expr, case_sensitive)
    math_interpreter.parse_algebra()

    # Get our variables together.
    all_variables, all_functions = add_defaults(variables, functions, case_sensitive)

    # ...and check them
    math_interpreter.check_variables(all_variables, all_functions)

    # Create a recursion to evaluate the tree.
    if case_sensitive:
        casify = lambda x: x
    else:
        casify = lambda x: x.lower()  # Lowercase for case insens.

    evaluate_actions = {
        'number': eval_number,
        'variable': lambda x: all_variables[casify(x[0])],
        'function': lambda x: all_functions[casify(x[0])](x[1]),
        'atom': eval_atom,
        'power': eval_power,
        'parallel': eval_parallel,
        'product': eval_product,
        'sum': eval_sum
    }

    return math_interpreter.reduce_tree(evaluate_actions)


class ParseAugmenter(object):
    """
    Holds the data for a particular parse.

    Retains the `math_expr` and `case_sensitive` so they needn't be passed
    around method to method.
    Eventually holds the parse tree and sets of variables as well.
    """
    def __init__(self, math_expr, case_sensitive=False):
        """
        Create the ParseAugmenter for a given math expression string.

        Do the parsing later, when called like `OBJ.parse_algebra()`.
        """
        self.case_sensitive = case_sensitive
        self.math_expr = math_expr
        self.tree = None
        self.variables_used = set()
        self.functions_used = set()

        def vpa(tokens):
            """
            When a variable is recognized, store it in `variables_used`.
            """
            varname = tokens[0][0]
            self.variables_used.add(varname)

        def fpa(tokens):
            """
            When a function is recognized, store it in `functions_used`.
            """
            varname = tokens[0][0]
            self.functions_used.add(varname)

        self.variable_parse_action = vpa
        self.function_parse_action = fpa

    def parse_algebra(self):
        """
        Parse an algebraic expression into a tree.

        Store a `pyparsing.ParseResult` in `self.tree` with proper groupings to
        reflect parenthesis and order of operations. Leave all operators in the
        tree and do not parse any strings of numbers into their float versions.

        Adding the groups and result names makes the `repr()` of the result
        really gross. For debugging, use something like
          print OBJ.tree.asXML()
        """
        # 0.33 or 7 or .34 or 16.
        number_part = Word(nums)
        inner_number = (number_part + Optional("." + Optional(number_part))) | ("." + number_part)
        # pyparsing allows spaces between tokens--`Combine` prevents that.
        inner_number = Combine(inner_number)

        # SI suffixes and percent.
        number_suffix = MatchFirst(Literal(k) for k in list(SUFFIXES.keys()))

        # 0.33k or 17
        plus_minus = Literal('+') | Literal('-')
        number = Group(
            Optional(plus_minus) +
            inner_number +
            Optional(CaselessLiteral("E") + Optional(plus_minus) + number_part) +
            Optional(number_suffix)
        )
        number = number("number")

        # Predefine recursive variables.
        expr = Forward()

        # Handle variables passed in. They must start with letters/underscores
        # and may contain numbers afterward.
        inner_varname = Word(alphas + "_", alphanums + "_")
        varname = Group(inner_varname)("variable")
        varname.setParseAction(self.variable_parse_action)

        # Same thing for functions.
        function = Group(inner_varname + Suppress("(") + expr + Suppress(")"))("function")
        function.setParseAction(self.function_parse_action)

        atom = number | function | varname | "(" + expr + ")"
        atom = Group(atom)("atom")

        # Do the following in the correct order to preserve order of operation.
        pow_term = atom + ZeroOrMore("^" + atom)
        pow_term = Group(pow_term)("power")

        par_term = pow_term + ZeroOrMore('||' + pow_term)  # 5k || 4k
        par_term = Group(par_term)("parallel")

        prod_term = par_term + ZeroOrMore((Literal('*') | Literal('/')) + par_term)  # 7 * 5 / 4
        prod_term = Group(prod_term)("product")

        sum_term = Optional(plus_minus) + prod_term + ZeroOrMore(plus_minus + prod_term)  # -5 + 4 - 3
        sum_term = Group(sum_term)("sum")

        # Finish the recursion.
        expr << sum_term  # pylint: disable=W0104
        self.tree = (expr + stringEnd).parseString(self.math_expr)[0]

    def reduce_tree(self, handle_actions, terminal_converter=None):
        """
        Call `handle_actions` recursively on `self.tree` and return result.

        `handle_actions` is a dictionary of node names (e.g. 'product', 'sum',
        etc&) to functions. These functions are of the following form:
         -input: a list of processed child nodes. If it includes any terminal
          nodes in the list, they will be given as their processed forms also.
         -output: whatever to be passed to the level higher, and what to
          return for the final node.
        `terminal_converter` is a function that takes in a token and returns a
        processed form. The default of `None` just leaves them as strings.
        """
        def handle_node(node):
            """
            Return the result representing the node, using recursion.

            Call the appropriate `handle_action` for this node. As its inputs,
            feed it the output of `handle_node` for each child node.
            """
            if not isinstance(node, ParseResults):
                # Then treat it as a terminal node.
                if terminal_converter is None:
                    return node
                else:
                    return terminal_converter(node)

            node_name = node.getName()
            if node_name not in handle_actions:  # pragma: no cover
                raise Exception("Unknown branch name '{}'".format(node_name))

            action = handle_actions[node_name]
            handled_kids = [handle_node(k) for k in node]
            return action(handled_kids)

        # Find the value of the entire tree.
        return handle_node(self.tree)

    def check_variables(self, valid_variables, valid_functions):
        """
        Confirm that all the variables used in the tree are valid/defined.

        Otherwise, raise an UndefinedVariable containing all bad variables.
        """
        if self.case_sensitive:
            casify = lambda x: x
        else:
            casify = lambda x: x.lower()  # Lowercase for case insens.

        # Test if casify(X) is valid, but return the actual bad input (i.e. X)
        bad_vars = set(var for var in self.variables_used
                       if casify(var) not in valid_variables)
        bad_vars.update(func for func in self.functions_used
                        if casify(func) not in valid_functions)

        if bad_vars:
            raise UndefinedVariable(' '.join(sorted(bad_vars)))

#-----------------------------------------------------------------------------

class LatexRendered(object):
    """
    Data structure to hold a typeset representation of some math.

    Fields:
     -`latex` is a generated, valid latex string (as if it were standalone).
     -`sans_parens` is usually the same as `latex` except without the outermost
      parens (if applicable).
     -`tall` is a boolean representing if the latex has any elements extending
      above or below a normal height, specifically things of the form 'a^b' and
      '\frac{a}{b}'. This affects the height of wrapping parenthesis.
    """
    def __init__(self, latex, parens=None, tall=False):
        """
        Instantiate with the latex representing the math.

        Optionally include parenthesis to wrap around it and the height.
        `parens` must be one of '(', '[' or '{'.
        `tall` is a boolean (see note above).
        """
        self.latex = latex
        self.sans_parens = latex
        self.tall = tall

        # Generate parens and overwrite `self.latex`.
        if parens is not None:
            left_parens = parens
            if left_parens == '{':
                left_parens = r'\{'

            pairs = {'(': ')',
                     '[': ']',
                     r'\{': r'\}'}
            if left_parens not in pairs:
                raise Exception(
                    "Unknown parenthesis '{}': coder error".format(left_parens)
                )
            right_parens = pairs[left_parens]

            if self.tall:
                left_parens = r"\left" + left_parens
                right_parens = r"\right" + right_parens

            self.latex = "{left}{expr}{right}".format(
                left=left_parens,
                expr=latex,
                right=right_parens
            )

    def __repr__(self):  # pragma: no cover
        """
        Give a sensible representation of the object.

        If `sans_parens` is different, include both.
        If `tall` then have '<[]>' around the code, otherwise '<>'.
        """
        if self.latex == self.sans_parens:
            latex_repr = '"{}"'.format(self.latex)
        else:
            latex_repr = '"{}" or "{}"'.format(self.latex, self.sans_parens)

        if self.tall:
            wrap = '<[{}]>'
        else:
            wrap = '<{}>'

        return wrap.format(latex_repr)


def render_number(children):
    """
    Combine the elements forming the number, escaping the suffix if needed.
    """
    children_latex = [k.latex for k in children]

    suffix = ""
    if children_latex[-1] in SUFFIXES:
        suffix = children_latex.pop()
        suffix = r"\text{{{s}}}".format(s=suffix)

    # Exponential notation-- the "E" splits the mantissa and exponent
    if "E" in children_latex:
        pos = children_latex.index("E")
        mantissa = "".join(children_latex[:pos])
        exponent = "".join(children_latex[pos + 1:])
        latex = r"{m}\!\times\!10^{{{e}}}{s}".format(
            m=mantissa, e=exponent, s=suffix
        )
        return LatexRendered(latex, tall=True)
    else:
        easy_number = "".join(children_latex)
        return LatexRendered(easy_number + suffix)


def enrich_varname(varname):
    """
    Prepend a backslash if we're given a greek character.
    """
    greek = ("alpha beta gamma delta epsilon varepsilon zeta eta theta "
             "vartheta iota kappa lambda mu nu xi pi rho sigma tau upsilon "
             "phi varphi chi psi omega").split()

    # add capital greek letters
    greek += [x.capitalize() for x in greek]

    # add hbar for QM
    greek.append('hbar')

    # add infinity
    greek.append('infty')

    if varname in greek:
        return r"\{letter}".format(letter=varname)
    else:
        return varname.replace("_", r"\_")


def variable_closure(variables, casify):
    """
    Wrap `render_variable` so it knows the variables allowed.
    """
    def render_variable(children):
        """
        Replace greek letters, otherwise escape the variable names.
        """
        varname = children[0].latex
        if casify(varname) not in variables:
            pass  # TODO turn unknown variable red or give some kind of error

        first, _, second = varname.partition("_")

        if second:
            # Then 'a_b' must become 'a_{b}'
            varname = r"{a}_{{{b}}}".format(
                a=enrich_varname(first),
                b=enrich_varname(second)
            )
        else:
            varname = enrich_varname(varname)

        return LatexRendered(varname)  # .replace("_", r"\_"))
    return render_variable


def function_closure(functions, casify):
    """
    Wrap `render_function` so it knows the functions allowed.
    """
    def render_function(children):
        """
        Escape function names and give proper formatting to exceptions.

        The exceptions being 'sqrt', 'log2', and 'log10' as of now.
        """
        fname = children[0].latex
        if casify(fname) not in functions:
            pass  # TODO turn unknown function red or give some kind of error

        # Wrap the input of the function with parens or braces.
        inner = children[1].latex
        if fname == "sqrt":
            inner = "{{{expr}}}".format(expr=inner)
        else:
            if children[1].tall:
                inner = r"\left({expr}\right)".format(expr=inner)
            else:
                inner = "({expr})".format(expr=inner)

        # Correctly format the name of the function.
        if fname == "sqrt":
            fname = r"\sqrt"
        elif fname == "log10":
            fname = r"\log_{10}"
        elif fname == "log2":
            fname = r"\log_2"
        else:
            fname = r"\text{{{fname}}}".format(fname=fname)

        # Put it together.
        latex = fname + inner
        return LatexRendered(latex, tall=children[1].tall)
    # Return the function within the closure.
    return render_function


def render_power(children):
    """
    Combine powers so that the latex is wrapped in curly braces correctly.

    Also, if you have 'a^(b+c)' don't include that last set of parens:
    'a^{b+c}' is correct, whereas 'a^{(b+c)}' is extraneous.
    """
    if len(children) == 1:
        return children[0]

    children_latex = [k.latex for k in children if k.latex != "^"]
    children_latex[-1] = children[-1].sans_parens

    raise_power = lambda x, y: "{}^{{{}}}".format(y, x)
    latex = reduce(raise_power, reversed(children_latex))
    return LatexRendered(latex, tall=True)


def render_parallel(children):
    """
    Simply join the child nodes with a double vertical line.
    """
    if len(children) == 1:
        return children[0]

    children_latex = [k.latex for k in children if k.latex != "||"]
    latex = r"\|".join(children_latex)
    tall = any(k.tall for k in children)
    return LatexRendered(latex, tall=tall)


def render_frac(numerator, denominator):
    r"""
    Given a list of elements in the numerator and denominator, return a '\frac'

    Avoid parens if they are unnecessary (i.e. the only thing in that part).
    """
    if len(numerator) == 1:
        num_latex = numerator[0].sans_parens
    else:
        num_latex = r"\cdot ".join(k.latex for k in numerator)

    if len(denominator) == 1:
        den_latex = denominator[0].sans_parens
    else:
        den_latex = r"\cdot ".join(k.latex for k in denominator)

    latex = r"\frac{{{num}}}{{{den}}}".format(num=num_latex, den=den_latex)
    return latex


def render_product(children):
    r"""
    Format products and division nicely.

    Group bunches of adjacent, equal operators. Every time it switches from
    denominator to the next numerator, call `render_frac`. Join these groupings
    together with '\cdot's, ending on a numerator if needed.

    Examples: (`children` is formed indirectly by the string on the left)
      'a*b' -> 'a\cdot b'
      'a/b' -> '\frac{a}{b}'
      'a*b/c/d' -> '\frac{a\cdot b}{c\cdot d}'
      'a/b*c/d*e' -> '\frac{a}{b}\cdot \frac{c}{d}\cdot e'
    """
    if len(children) == 1:
        return children[0]

    position = "numerator"  # or denominator
    fraction_mode_ever = False
    numerator = []
    denominator = []
    latex = ""

    for kid in children:
        if position == "numerator":
            if kid.latex == "*":
                pass  # Don't explicitly add the '\cdot' yet.
            elif kid.latex == "/":
                # Switch to denominator mode.
                fraction_mode_ever = True
                position = "denominator"
            else:
                numerator.append(kid)
        else:
            if kid.latex == "*":
                # Switch back to numerator mode.
                # First, render the current fraction and add it to the latex.
                latex += render_frac(numerator, denominator) + r"\cdot "

                # Reset back to beginning state
                position = "numerator"
                numerator = []
                denominator = []
            elif kid.latex == "/":
                pass  # Don't explicitly add a '\frac' yet.
            else:
                denominator.append(kid)

    # Add the fraction/numerator that we ended on.
    if position == "denominator":
        latex += render_frac(numerator, denominator)
    else:
        # We ended on a numerator--act like normal multiplication.
        num_latex = r"\cdot ".join(k.latex for k in numerator)
        latex += num_latex

    tall = fraction_mode_ever or any(k.tall for k in children)
    return LatexRendered(latex, tall=tall)


def render_sum(children):
    """
    Concatenate elements, including the operators.
    """
    if len(children) == 1:
        return children[0]

    children_latex = [k.latex for k in children]
    latex = "".join(children_latex)
    tall = any(k.tall for k in children)
    return LatexRendered(latex, tall=tall)


def render_atom(children):
    """
    Properly handle parens, otherwise this is trivial.
    """
    if len(children) == 3:
        return LatexRendered(
            children[1].latex,
            parens=children[0].latex,
            tall=children[1].tall
        )
    else:
        return children[0]


def add_defaults(var, fun, case_sensitive=False):
    """
    Create sets with both the default and user-defined variables.

    Compare to calc.add_defaults
    """
    var_items = set(DEFAULT_VARIABLES)
    fun_items = set(DEFAULT_FUNCTIONS)

    var_items.update(var)
    fun_items.update(fun)

    if not case_sensitive:
        var_items = set(k.lower() for k in var_items)
        fun_items = set(k.lower() for k in fun_items)

    return var_items, fun_items


def latex_preview(math_expr, variables=(), functions=(), case_sensitive=False):
    """
    Convert `math_expr` into latex, guaranteeing its parse-ability.

    Analagous to `evaluator`.
    """
    # No need to go further
    if math_expr.strip() == "":
        return ""

    # Parse tree
    latex_interpreter = ParseAugmenter(math_expr, case_sensitive)
    latex_interpreter.parse_algebra()

    # Get our variables together.
    variables, functions = add_defaults(variables, functions, case_sensitive)

    # Create a recursion to evaluate the tree.
    if case_sensitive:
        casify = lambda x: x
    else:
        casify = lambda x: x.lower()  # Lowercase for case insens.

    render_actions = {
        'number': render_number,
        'variable': variable_closure(variables, casify),
        'function': function_closure(functions, casify),
        'atom': render_atom,
        'power': render_power,
        'parallel': render_parallel,
        'product': render_product,
        'sum': render_sum
    }

    backslash = "\\"
    wrap_escaped_strings = lambda s: LatexRendered(
        s.replace(backslash, backslash * 2)
    )

    output = latex_interpreter.reduce_tree(
        render_actions,
        terminal_converter=wrap_escaped_strings
    )
    return output.latex
