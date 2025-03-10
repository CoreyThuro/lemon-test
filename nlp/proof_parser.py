"""
Proof parser for mathematical proofs.
Parses natural language proofs into structured representations.
"""

import re
import spacy
from typing import Dict, List, Tuple, Any, Union, Optional
from sympy.parsing.sympy_parser import parse_expr, TokenError
from sympy import symbols

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    raise ImportError("spaCy model 'en_core_web_sm' not found. Please install with 'python -m spacy download en_core_web_sm'")

# Mathematical concept mapping
MATH_CONCEPTS = {
    "natural number": "nat",
    "integer": "Z",
    "real number": "R",
    "even": lambda x: f"exists k : nat, {x} = 2 * k",
    "odd": lambda x: f"exists k : nat, {x} = 2 * k + 1",
    "prime": lambda x: f"prime {x}",
    "divisible": lambda x, y: f"exists k : nat, {x} = k * {y}",
}

# Logical structure mapping
LOGICAL_MARKERS = {
    "assume": "intros",
    "suppose": "intros",
    "let": "intros",
    "if": "intros",
    "then": "assert",
    "therefore": "assert",
    "thus": "assert",
    "hence": "assert",
    "by": None,  # Requires context
    "because": None,  # Requires context
    "since": None,  # Requires context
    "we know": "assert",
    "we have": "assert",
}

# Proof method mapping
PROOF_METHODS = {
    "induction": "induction",
    "contradiction": "contradiction",
    "case": "destruct",
    "cases": "destruct",
    "direct": None,  # Direct proof doesn't need a special tactic
}

def extract_variables(doc):
    """Extract potential mathematical variables from text"""
    variables = []
    for token in doc:
        # Look for single letter tokens that might be variables
        if (len(token.text) == 1 and token.text.isalpha() and 
            token.pos_ not in ["DET", "CCONJ", "ADP"]):
            variables.append(token.text)
    return list(set(variables))

def extract_mathematical_expressions(text):
    """Extract potential mathematical expressions"""
    # Simple pattern for basic math expressions (x+y, 2*z, etc.)
    expr_pattern = r'\b([a-zA-Z][a-zA-Z0-9]*(?:\s*[\+\-\*\/\^\=]\s*[a-zA-Z0-9]+)+)'
    expressions = re.findall(expr_pattern, text)
    
    # Try to parse with sympy if possible
    parsed_expressions = []
    for expr in expressions:
        try:
            # Create symbols for variables in the expression
            var_pattern = r'[a-zA-Z]+'
            vars_in_expr = re.findall(var_pattern, expr)
            for var in vars_in_expr:
                exec(f"{var} = symbols('{var}')")
            
            # Parse the expression with sympy
            parsed = parse_expr(expr)
            parsed_expressions.append((expr, str(parsed)))
        except (TokenError, SyntaxError, NameError):
            # If sympy parsing fails, just keep the original
            parsed_expressions.append((expr, expr))
    
    return parsed_expressions

def identify_proof_structure(statements):
    """Identify the overall structure of the proof"""
    structure = {
        "assumptions": [],
        "conclusions": [],
        "proof_methods": [],
        "variables": [],
        "expressions": [],
    }
    
    for statement in statements:
        statement_text = " ".join([token[0] for token in statement])
        doc = nlp(statement_text)
        
        # Look for logical markers
        for marker, tactic in LOGICAL_MARKERS.items():
            if marker in statement_text.lower():
                if marker in ["assume", "suppose", "let", "if"]:
                    structure["assumptions"].append((statement_text, tactic))
                elif marker in ["then", "therefore", "thus", "hence", "we know", "we have"]:
                    structure["conclusions"].append((statement_text, tactic))
        
        # Look for proof methods
        for method, tactic in PROOF_METHODS.items():
            if method in statement_text.lower():
                structure["proof_methods"].append((method, tactic, statement_text))
        
        # Extract variables
        structure["variables"].extend(extract_variables(doc))
        
        # Extract mathematical expressions
        expressions = extract_mathematical_expressions(statement_text)
        structure["expressions"].extend(expressions)
    
    return structure

def split_theorem_and_proof(text: str) -> Tuple[str, str]:
    """
    Split the input text into theorem statement and proof.
    
    Args:
        text: The input text containing theorem and proof
        
    Returns:
        Tuple of (theorem_statement, proof_text)
    """
    # Look for "Proof:" or similar markers
    proof_markers = [
        r'Proof[\s\:]+',
        r'Proof[\s\.]+'
    ]
    
    for marker in proof_markers:
        match = re.search(marker, text, re.IGNORECASE)
        if match:
            split_index = match.start()
            theorem = text[:split_index].strip()
            proof = text[match.end():].strip()
            return theorem, proof
    
    # No explicit marker found, try to infer
    lines = text.split("\n")
    
    # If short, single line, it's likely just a theorem
    if len(lines) <= 1:
        return text, ""
    
    # Otherwise, first line is often the theorem
    theorem = lines[0].strip()
    proof = "\n".join(lines[1:]).strip()
    
    return theorem, proof

def parse_proof(text: str, depth=0, max_depth=1000) -> Tuple[List[Any], Dict[str, Any]]:
    """
    Parse proof text and extract logical structure.
    
    Args:
        text: The proof text
        depth: Current recursion depth
        max_depth: Maximum recursion depth
        
    Returns:
        Tuple of (parsed_statements, proof_structure)
    """
    if depth > max_depth:
        raise RecursionError("Maximum recursion depth exceeded")
    
    # Split into theorem and proof if needed
    theorem_text, proof_text = split_theorem_and_proof(text)
    
    # If proof_text is empty, the entire text is the proof
    if not proof_text:
        proof_text = text
    
    # Base case: if proof_text is empty
    if not proof_text.strip():
        return [], {}
    
    # Process the text
    doc = nlp(proof_text)
    
    # Extract statements from sentences
    parsed_statements = []
    for sent in doc.sents:
        tokens = [(token.text, token.pos_, token.dep_) for token in sent]
        parsed_statements.append(tokens)
    
    # Identify the proof structure
    proof_structure = identify_proof_structure(parsed_statements)
    
    return parsed_statements, proof_structure

def parse_theorem_and_proof(text: str) -> Tuple[str, str, List[Any], Dict[str, Any]]:
    """
    Parse both theorem and proof from text.
    
    Args:
        text: The input text containing theorem and proof
        
    Returns:
        Tuple of (theorem_text, proof_text, parsed_statements, proof_structure)
    """
    # Split into theorem and proof
    theorem_text, proof_text = split_theorem_and_proof(text)
    
    # Parse the proof
    parsed_statements, proof_structure = parse_proof(proof_text)
    
    return theorem_text, proof_text, parsed_statements, proof_structure

def preprocess_text(text: str) -> str:
    """
    Preprocess the text to normalize mathematical notation.
    
    Args:
        text: The input text
        
    Returns:
        Normalized text
    """
    # Replace common mathematical symbols
    replacements = {
        '∀': 'for all',
        '∃': 'there exists',
        '∈': 'in',
        '⊆': 'subset of',
        '⊂': 'proper subset of',
        '∩': 'intersection',
        '∪': 'union',
        '⇒': 'implies',
        '→': 'implies',
        '⟹': 'implies',
        '⟺': 'if and only if',
        '⟷': 'if and only if',
        '≠': 'not equal to',
        '≤': 'less than or equal to',
        '≥': 'greater than or equal to',
        '≡': 'equivalent to',
        '≈': 'approximately equal to',
        '∞': 'infinity',
        '√': 'square root of',
        '∑': 'sum',
        '∏': 'product',
        '∫': 'integral',
        '∂': 'partial'
    }
    
    for symbol, replacement in replacements.items():
        text = text.replace(symbol, f' {replacement} ')
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# Main function for external use
def parse_math_proof(text: str) -> Dict[str, Any]:
    """
    Parse a mathematical proof and return structured information.
    
    Args:
        text: The input text containing theorem and proof
        
    Returns:
        Dictionary with parsed information
    """
    # Preprocess text
    preprocessed_text = preprocess_text(text)
    
    # Split and parse
    theorem_text, proof_text, parsed_statements, proof_structure = parse_theorem_and_proof(preprocessed_text)
    
    return {
        "theorem_text": theorem_text,
        "proof_text": proof_text,
        "parsed_statements": parsed_statements,
        "proof_structure": proof_structure,
        "original_text": text
    }