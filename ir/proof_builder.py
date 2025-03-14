"""
Builder for constructing proof intermediate representations.
Translates parsed proofs into the IR structure.
"""

from typing import Dict, List, Tuple, Any, Optional, Union
import re
import logging

from ir.proof_ir import (
    ProofIR, ProofNode, Expression, NodeType, ExprType, TacticType, TacticInfo,
    create_theorem_node, create_assumption_node, create_step_node, create_conclusion_node,
    DomainContext, LibraryDependency
)

# Import the knowledge base
try:
    from knowledge_base.domain_kb import DomainKnowledgeBase
except ImportError:
    # If knowledge base is not available, use a placeholder
    class DomainKnowledgeBase:
        def __init__(self, data_dir=None):
            pass
        
        def get_libraries_for_concept(self, concept, domain=None, prover="coq"):
            return []
        
        def get_domain_libraries(self, domain, prover="coq"):
            return []

logger = logging.getLogger("proof_builder")

class ProofBuilder:
    """
    Builds a ProofIR from parsed proof data.
    """
    
    def __init__(self):
        """Initialize the builder."""
        # Initialize the knowledge base
        self.kb = DomainKnowledgeBase()
    
    def build_from_parsed(self, 
                         theorem_text: str, 
                         parsed_proof: Tuple[List[List[Tuple[str, str, str]]], Dict[str, Any]],
                         original_proof_text: str) -> ProofIR:
        """
        Build a ProofIR from parsed theorem and proof.
        
        Args:
            theorem_text: The original theorem text
            parsed_proof: The output from the proof parser (statements, structure)
            original_proof_text: The original proof text
            
        Returns:
            A ProofIR object representing the proof
        """
        parsed_statements, proof_structure = parsed_proof
        
        # Create the theorem node
        theorem_node = create_theorem_node(theorem_text)
        
        # Build the proof tree
        proof_tree = self._build_proof_tree(parsed_statements, proof_structure)
        
        # Identify domain
        domain_info = self._identify_domain(theorem_text, original_proof_text, proof_structure)
        
        # Identify pattern
        pattern_info = self._identify_pattern(proof_structure)
        
        # Generate tactics
        tactics = self._generate_tactics(proof_structure, domain_info)
        
        # Create the IR
        proof_ir = ProofIR(
            theorem=theorem_node,
            proof_tree=proof_tree,
            domain=domain_info,
            pattern=pattern_info,
            tactics=tactics,
            original_theorem=theorem_text,
            original_proof=original_proof_text
        )
        
        # Add domain-specific knowledge to IR
        self._add_domain_context(proof_ir, domain_info, proof_structure)
        
        return proof_ir
    
    def _build_proof_tree(self, 
                        parsed_statements: List[List[Tuple[str, str, str]]], 
                        proof_structure: Dict[str, Any]) -> List[ProofNode]:
        """
        Build the proof tree from parsed statements and structure.
        
        Args:
            parsed_statements: The parsed statements from the proof
            proof_structure: The structure information from the parser
            
        Returns:
            A list of ProofNode objects representing the proof tree
        """
        # List to store the proof nodes
        proof_tree = []
        
        # Track which statements have been processed
        processed_statements = set()
        
        # Process assumptions first
        for assumption_text, tactic in proof_structure.get("assumptions", []):
            # Find the corresponding statement
            for i, statement in enumerate(parsed_statements):
                statement_text = " ".join([token[0] for token in statement])
                if statement_text == assumption_text and i not in processed_statements:
                    assumption_node = create_assumption_node(statement_text)
                    assumption_node.metadata["tactic"] = tactic
                    proof_tree.append(assumption_node)
                    processed_statements.add(i)
                    break
        
        # Process any special proof methods (induction, contradiction, etc.)
        for method, tactic, statement_text in proof_structure.get("proof_methods", []):
            # Find the corresponding statement
            for i, statement in enumerate(parsed_statements):
                curr_statement_text = " ".join([token[0] for token in statement])
                if curr_statement_text == statement_text and i not in processed_statements:
                    # Create appropriate node based on the method
                    if method == "induction":
                        # Create a parent node for induction
                        induction_node = ProofNode(
                            node_type=NodeType.STEP,
                            content=f"Induction on {self._extract_induction_variable(statement_text)}",
                            metadata={"method": method, "tactic": tactic}
                        )
                        
                        # Create placeholders for base and inductive steps
                        # (In a real implementation, we'd need to find the actual statements)
                        base_node = ProofNode(
                            node_type=NodeType.INDUCTION_BASE,
                            content="Base case",
                            metadata={"method": "base_case"}
                        )
                        
                        inductive_node = ProofNode(
                            node_type=NodeType.INDUCTION_STEP,
                            content="Inductive step",
                            metadata={"method": "inductive_step"}
                        )
                        
                        # Add as children of the induction node
                        induction_node.children = [base_node, inductive_node]
                        proof_tree.append(induction_node)
                    
                    elif method == "contradiction":
                        contradiction_node = ProofNode(
                            node_type=NodeType.CONTRADICTION,
                            content=curr_statement_text,
                            metadata={"method": method, "tactic": tactic}
                        )
                        proof_tree.append(contradiction_node)
                    
                    elif method in ["case", "cases"]:
                        case_node = ProofNode(
                            node_type=NodeType.CASE,
                            content=curr_statement_text,
                            metadata={"method": method, "tactic": tactic}
                        )
                        proof_tree.append(case_node)
                    
                    else:
                        # Generic step node for other methods
                        step_node = create_step_node(curr_statement_text)
                        step_node.metadata["method"] = method
                        step_node.metadata["tactic"] = tactic
                        proof_tree.append(step_node)
                    
                    processed_statements.add(i)
                    break
        
        # Process conclusions
        for conclusion_text, tactic in proof_structure.get("conclusions", []):
            # Find the corresponding statement
            for i, statement in enumerate(parsed_statements):
                statement_text = " ".join([token[0] for token in statement])
                if statement_text == conclusion_text and i not in processed_statements:
                    if i == len(parsed_statements) - 1:
                        # Last statement is the final conclusion
                        conclusion_node = create_conclusion_node(statement_text)
                        conclusion_node.metadata["tactic"] = tactic
                        proof_tree.append(conclusion_node)
                    else:
                        # Intermediate conclusion (assertion)
                        step_node = create_step_node(statement_text)
                        step_node.metadata["tactic"] = tactic
                        proof_tree.append(step_node)
                    
                    processed_statements.add(i)
                    break
        
        # Process any remaining statements as regular steps
        for i, statement in enumerate(parsed_statements):
            if i not in processed_statements:
                statement_text = " ".join([token[0] for token in statement])
                step_node = create_step_node(statement_text)
                proof_tree.append(step_node)
        
        return proof_tree
    
    def _identify_domain(self, 
                        theorem_text: str, 
                        proof_text: str, 
                        proof_structure: Dict[str, Any]) -> Dict[str, Any]:
        """
        Identify the mathematical domain of the proof.
        
        Args:
            theorem_text: The theorem text
            proof_text: The proof text
            proof_structure: The structure information from the parser
            
        Returns:
            A dictionary with domain information
        """
        # Combine texts for analysis
        combined_text = f"{theorem_text} {proof_text}".lower()
        
        # Define domain keywords
        domain_keywords = {
            "number_theory": ["prime", "divisible", "gcd", "modulo", "congruence", "integer", "factor", "even", "odd"],
            "algebra": ["group", "ring", "field", "vector", "space", "linear", "matrix", "determinant"],
            "topology": ["open", "closed", "continuous", "compact", "connected", "neighborhood", "metric"],
            "analysis": ["limit", "derivative", "integral", "convergence", "sequence", "series", "function"],
            "geometry": ["triangle", "circle", "angle", "polygon", "distance", "line", "plane"],
            "set_theory": ["set", "subset", "union", "intersection", "complement", "element", "belongs"]
        }
        
        # Map domain names to MSC codes
        domain_to_msc = {
            "number_theory": "11",
            "algebra": "12-20",
            "topology": "54-55",
            "analysis": "26-42",
            "geometry": "51-53",
            "set_theory": "03"
        }
        
        # Count occurrences of keywords in each domain
        domain_scores = {domain: 0 for domain in domain_keywords}
        
        for domain, keywords in domain_keywords.items():
            for keyword in keywords:
                if keyword in combined_text:
                    # Count occurrences
                    count = combined_text.count(keyword)
                    domain_scores[domain] += count
        
        # Determine the most likely domain
        max_score = max(domain_scores.values())
        if max_score > 0:
            primary_domain = max(domain_scores.items(), key=lambda x: x[1])[0]
            msc_code = domain_to_msc.get(primary_domain, "00")
        else:
            primary_domain = "general_mathematics"
            msc_code = "00"
        
        # Check if the proof involves natural numbers or integers specifically
        is_discrete = any(term in combined_text for term in ["natural number", "integer", "even", "odd", "divisible"])
        
        # Check for evenness proofs specifically
        is_evenness = "even" in combined_text and any(f"{var} + {var}" in combined_text for var in "abcdefghijklmnopqrstuvwxyz")
        
        return {
            "primary_domain": msc_code,
            "domain_name": primary_domain,
            "confidence": max_score / (sum(domain_scores.values()) or 1),
            "involves_discrete": is_discrete,
            "is_evenness_proof": is_evenness,
            "domain_scores": domain_scores
        }
    
    def _identify_pattern(self, proof_structure: Dict[str, Any]) -> Dict[str, Any]:
        """
        Identify the proof pattern.
        
        Args:
            proof_structure: The structure information from the parser
            
        Returns:
            A dictionary with pattern information
        """
        # Check if there are any explicit proof methods
        methods = [method for method, _, _ in proof_structure.get("proof_methods", [])]
        
        pattern = {}
        
        if "induction" in methods:
            pattern = {
                "name": "induction",
                "confidence": 1.0,
                "description": "Proof by induction"
            }
        elif "contradiction" in methods:
            pattern = {
                "name": "contradiction",
                "confidence": 1.0,
                "description": "Proof by contradiction"
            }
        elif any(method in methods for method in ["case", "cases"]):
            pattern = {
                "name": "case_analysis",
                "confidence": 1.0,
                "description": "Proof by case analysis"
            }
        else:
            # No explicit method mentioned, infer from structure
            
            # Count statements with "assume" or "let" at the beginning
            assumption_count = len(proof_structure.get("assumptions", []))
            
            # Count statements with "therefore", "thus", "hence" at the beginning
            conclusion_count = len(proof_structure.get("conclusions", []))
            
            if assumption_count > 0 and "even" in str(proof_structure):
                # Check for evenness proofs (special case in our system)
                pattern = {
                    "name": "evenness_proof",
                    "confidence": 0.8,
                    "description": "Proof of an evenness property"
                }
            elif assumption_count == 1 and conclusion_count >= 1:
                # Simple direct proof (one assumption, one or more conclusions)
                pattern = {
                    "name": "direct",
                    "confidence": 0.7,
                    "description": "Direct proof"
                }
            else:
                # Default case
                pattern = {
                    "name": "unknown",
                    "confidence": 0.5,
                    "description": "Unknown proof pattern"
                }
        
        return pattern
    
    def _generate_tactics(self, 
                        proof_structure: Dict[str, Any], 
                        domain_info: Dict[str, Any]) -> List[TacticInfo]:
        """
        Generate tactic suggestions based on the proof structure and domain.
        
        Args:
            proof_structure: The structure information from the parser
            domain_info: The domain information
            
        Returns:
            A list of TacticInfo objects
        """
        tactics = []
        
        # Add intros tactic for assumptions
        if proof_structure.get("assumptions", []):
            # Extract variables from assumptions
            variables = [var for var in proof_structure.get("variables", []) if var.isalpha()]
            
            tactics.append(TacticInfo(
                tactic_type=TacticType.INTRO,
                arguments=variables,
                description="Introduce variables and hypotheses"
            ))
        
        # Add specific tactics based on proof methods
        methods = [method for method, _, _ in proof_structure.get("proof_methods", [])]
        
        if "induction" in methods:
            # Find the variable being inducted on
            induction_var = None
            for _, _, statement in proof_structure.get("proof_methods", []):
                if "induction" in statement.lower():
                    # Extract the variable after "induction on"
                    match = re.search(r'induction on\s+([a-zA-Z])', statement, re.IGNORECASE)
                    if match:
                        induction_var = match.group(1)
                        break
            
            if induction_var:
                tactics.append(TacticInfo(
                    tactic_type=TacticType.INDUCTION,
                    arguments=[induction_var],
                    description=f"Induction on {induction_var}"
                ))
        
        if "contradiction" in methods:
            tactics.append(TacticInfo(
                tactic_type=TacticType.CONTRADICTION,
                arguments=[],
                description="Proof by contradiction"
            ))
        
        if any(method in methods for method in ["case", "cases"]):
            tactics.append(TacticInfo(
                tactic_type=TacticType.CASE_ANALYSIS,
                arguments=[],
                description="Case analysis"
            ))
        
        # Add domain-specific tactics
        domain = domain_info.get("primary_domain")
        
        if domain == "11":  # Number Theory
            # Check for evenness proof
            if domain_info.get("is_evenness_proof", False):
                tactics.append(TacticInfo(
                    tactic_type=TacticType.EXISTS,
                    arguments=["n"],
                    description="Provide witness for existential"
                ))
                tactics.append(TacticInfo(
                    tactic_type=TacticType.CUSTOM,
                    arguments=["ring"],
                    description="Use ring tactic for algebraic simplification"
                ))
            else:
                tactics.append(TacticInfo(
                    tactic_type=TacticType.CUSTOM,
                    arguments=["lia"],
                    description="Use linear integer arithmetic solver"
                ))
        
        # Add a default simplification tactic
        if not any(t.tactic_type == TacticType.SIMPLIFY for t in tactics):
            tactics.append(TacticInfo(
                tactic_type=TacticType.SIMPLIFY,
                arguments=[],
                description="Simplify expressions"
            ))
        
        return tactics
    
    def _extract_induction_variable(self, statement_text: str) -> str:
        """
        Extract the variable being inducted on from a statement.
        
        Args:
            statement_text: The statement text
            
        Returns:
            The induction variable, or 'n' as a default
        """
        # Look for patterns like "induction on x", "by induction on n", etc.
        match = re.search(r'induction on\s+([a-zA-Z])', statement_text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Default to 'n' if no variable is found
        return 'n'
    
    def _add_domain_context(self, proof_ir: ProofIR, domain_info: Dict[str, Any], proof_structure: Dict[str, Any]) -> None:
        """
        Add domain-specific context to the IR.
        
        Args:
            proof_ir: The proof IR
            domain_info: The domain information
            proof_structure: The proof structure
        """
        # Get domain from domain info
        domain = domain_info.get("primary_domain", "00")
        
        # Create or update domain context
        if proof_ir.domain_context is None:
            proof_ir.domain_context = DomainContext(domain)
        else:
            proof_ir.domain_context.domain = domain
        
        # Add domain libraries
        libraries = self.kb.get_domain_libraries(domain, "coq")
        proof_ir.domain_context.libraries.extend(libraries)
        
        # Add libraries for concepts mentioned in the proof
        concepts = self._extract_concepts(proof_ir)
        for concept in concepts:
            # Get libraries for this concept in this domain
            concept_libraries = self.kb.get_libraries_for_concept(concept, domain, "coq")
            for library in concept_libraries:
                if library not in proof_ir.domain_context.libraries:
                    proof_ir.domain_context.libraries.append(library)
                
                # Add library dependency to the IR
                proof_ir.add_library_dependency(library, f"Require Import {library}.", [concept])
        
        # Handle evenness proof specially
        if domain_info.get("is_evenness_proof", False):
            # Ensure we have the necessary libraries for evenness proofs
            if "Arith" not in proof_ir.domain_context.libraries:
                proof_ir.domain_context.libraries.append("Arith")
                proof_ir.add_library_dependency("Arith", "Require Import Arith.", ["even"])
            
            if "Ring" not in proof_ir.domain_context.libraries:
                proof_ir.domain_context.libraries.append("Ring")
                proof_ir.add_library_dependency("Ring", "Require Import Ring.", ["ring"])
    
    def _extract_concepts(self, proof_ir: ProofIR) -> List[str]:
        """
        Extract concepts mentioned in the proof.
        
        Args:
            proof_ir: The proof IR
            
        Returns:
            List of concepts
        """
        concepts = []
        
        # Extract variables from metadata
        variables = proof_ir.metadata.get("variables", [])
        concepts.extend(variables)
        
        # Extract concepts from theorem
        if isinstance(proof_ir.theorem.content, str):
            theorem_text = proof_ir.theorem.content
            # Look for common mathematical concepts
            if "even" in theorem_text.lower():
                concepts.append("even")
            if "odd" in theorem_text.lower():
                concepts.append("odd")
            if "prime" in theorem_text.lower():
                concepts.append("prime")
            if "divisible" in theorem_text.lower() or "divides" in theorem_text.lower():
                concepts.append("divisible")
        
        # Extract concepts from proof tree
        for node in proof_ir.proof_tree:
            if isinstance(node.content, str):
                node_text = node.content.lower()
                if "even" in node_text:
                    concepts.append("even")
                if "odd" in node_text:
                    concepts.append("odd")
                if "prime" in node_text:
                    concepts.append("prime")
                if "divisible" in node_text or "divides" in node_text:
                    concepts.append("divisible")
        
        # Extract concepts from the original proof
        if proof_ir.original_proof:
            proof_text = proof_ir.original_proof.lower()
            if "even" in proof_text:
                concepts.append("even")
            if "odd" in proof_text:
                concepts.append("odd")
            if "prime" in proof_text:
                concepts.append("prime")
            if "divisible" in proof_text or "divides" in proof_text:
                concepts.append("divisible")
        
        # Remove duplicates
        return list(set(concepts))
    
    def build_proof_ir(self, parsed_statements, proof_structure, original_theorem, original_proof):
        """
        Wrapper function that creates a ProofIR from parsed proof data.

        Args:
            parsed_statements: The parsed statements from the proof parser
            proof_structure: The structure information from the parser
            original_theorem: The original theorem text
            original_proof: The original proof text
                
        Returns:
            A ProofIR object representing the proof
        """
        parsed_proof = (parsed_statements, proof_structure)
        return self.build_from_parsed(original_theorem, parsed_proof, original_proof)