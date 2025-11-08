"""
Response validation utilities for mental health annotation domains.
"""
import re
import json
from typing import Tuple, Optional, List
from dataclasses import dataclass
import logging


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════

@dataclass
class ValidationResult:
    """Result of response validation."""
    label: Optional[str] = None
    parsing_error: Optional[str] = None
    validity_error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if validation result is valid."""
        return (self.parsing_error is None and
                self.validity_error is None and
                self.label is not None)


# ═══════════════════════════════════════════════════════════
# BASE RESPONSE PARSER
# ═══════════════════════════════════════════════════════════

class ResponseParser:
    """Base class for parsing AI model responses."""

    def extract_tag_content(self, response_text: str) -> Optional[str]:
        """
        Extract content from << >> tags.

        Args:
            response_text: Full response from AI model

        Returns:
            Extracted content or None if tags not found
        """
        match = re.search(r'<<(.+?)>>', response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def parse(self, response_text: str) -> ValidationResult:
        """
        Parse and validate response.

        Args:
            response_text: Full response from AI model

        Returns:
            ValidationResult object

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement parse()")


# ═══════════════════════════════════════════════════════════
# DOMAIN-SPECIFIC PARSERS
# ═══════════════════════════════════════════════════════════

class UrgencyParser(ResponseParser):
    """Parser for Urgency Level domain (LEVEL_0 to LEVEL_4)."""

    VALID_LEVELS = ['0', '1', '2', '3', '4']

    def parse(self, response_text: str) -> ValidationResult:
        """Parse urgency level response."""
        result = ValidationResult()

        # Extract tag content
        raw_label = self.extract_tag_content(response_text)
        if raw_label is None:
            result.parsing_error = "Could not find << >> tags in response"
            return result

        # Try to extract LEVEL_X pattern
        level_match = re.search(r'LEVEL[_\s]*([0-4])', raw_label, re.IGNORECASE)

        if level_match:
            level = level_match.group(1)
            if level in self.VALID_LEVELS:
                result.label = f"LEVEL_{level}"
            else:
                result.validity_error = f"Invalid urgency level: {level}. Must be 0-4."
        else:
            result.validity_error = f"Invalid urgency level format: '{raw_label}'. Expected LEVEL_X where X is 0-4."

        return result


class TherapeuticParser(ResponseParser):
    """Parser for Therapeutic Approach domain (TA-1 to TA-9, multi-label)."""

    VALID_CODES = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

    def parse(self, response_text: str) -> ValidationResult:
        """Parse therapeutic approach response."""
        result = ValidationResult()

        # Extract tag content
        raw_label = self.extract_tag_content(response_text)
        if raw_label is None:
            result.parsing_error = "Could not find << >> tags in response"
            return result

        # Extract TA-X codes
        codes = re.findall(r'TA-([1-9])', raw_label)

        if codes:
            # Remove duplicates while preserving order
            seen = set()
            unique_codes = []
            for code in codes:
                if code not in seen:
                    seen.add(code)
                    unique_codes.append(code)

            # Validate all codes
            invalid_codes = [c for c in unique_codes if c not in self.VALID_CODES]
            if invalid_codes:
                result.validity_error = f"Invalid therapeutic codes: {invalid_codes}"
            else:
                result.label = ", ".join([f"TA-{c}" for c in unique_codes])
        else:
            result.validity_error = f"No valid TA codes found in: '{raw_label}'. Expected TA-1 to TA-9."

        return result


class IntensityParser(ResponseParser):
    """Parser for Intervention Intensity domain (INT-1 to INT-5)."""

    VALID_LEVELS = ['1', '2', '3', '4', '5']

    def parse(self, response_text: str) -> ValidationResult:
        """Parse intervention intensity response."""
        result = ValidationResult()

        # Extract tag content
        raw_label = self.extract_tag_content(response_text)
        if raw_label is None:
            result.parsing_error = "Could not find << >> tags in response"
            return result

        # Try to extract INT-X pattern
        int_match = re.search(r'INT-([1-5])', raw_label, re.IGNORECASE)

        if int_match:
            level = int_match.group(1)
            if level in self.VALID_LEVELS:
                result.label = f"INT-{level}"
            else:
                result.validity_error = f"Invalid intensity level: {level}. Must be 1-5."
        else:
            result.validity_error = f"Invalid intensity format: '{raw_label}'. Expected INT-X where X is 1-5."

        return result


class AdjunctParser(ResponseParser):
    """Parser for Adjunct Services domain (ADJ-1 to ADJ-8, multi-label or NONE)."""

    VALID_CODES = ['1', '2', '3', '4', '5', '6', '7', '8']

    def parse(self, response_text: str) -> ValidationResult:
        """Parse adjunct services response."""
        result = ValidationResult()

        # Extract tag content
        raw_label = self.extract_tag_content(response_text)
        if raw_label is None:
            result.parsing_error = "Could not find << >> tags in response"
            return result

        # Check for NONE
        if "NONE" in raw_label.upper():
            result.label = "NONE"
            return result

        # Extract ADJ-X codes
        codes = re.findall(r'ADJ-([1-8])', raw_label)

        if codes:
            # Remove duplicates while preserving order
            seen = set()
            unique_codes = []
            for code in codes:
                if code not in seen:
                    seen.add(code)
                    unique_codes.append(code)

            # Validate all codes
            invalid_codes = [c for c in unique_codes if c not in self.VALID_CODES]
            if invalid_codes:
                result.validity_error = f"Invalid adjunct codes: {invalid_codes}"
            else:
                result.label = ", ".join([f"ADJ-{c}" for c in unique_codes])
        else:
            result.validity_error = f"No valid ADJ codes found in: '{raw_label}'. Expected ADJ-1 to ADJ-8 or NONE."

        return result


class ModalityParser(ResponseParser):
    """Parser for Treatment Modality domain (MOD-1 to MOD-6, multi-label)."""

    VALID_CODES = ['1', '2', '3', '4', '5', '6']

    def parse(self, response_text: str) -> ValidationResult:
        """Parse treatment modality response."""
        result = ValidationResult()

        # Extract tag content
        raw_label = self.extract_tag_content(response_text)
        if raw_label is None:
            result.parsing_error = "Could not find << >> tags in response"
            return result

        # Extract MOD-X codes
        codes = re.findall(r'MOD-([1-6])', raw_label)

        if codes:
            # Remove duplicates while preserving order
            seen = set()
            unique_codes = []
            for code in codes:
                if code not in seen:
                    seen.add(code)
                    unique_codes.append(code)

            # Validate all codes
            invalid_codes = [c for c in unique_codes if c not in self.VALID_CODES]
            if invalid_codes:
                result.validity_error = f"Invalid modality codes: {invalid_codes}"
            else:
                result.label = ", ".join([f"MOD-{c}" for c in unique_codes])
        else:
            result.validity_error = f"No valid MOD codes found in: '{raw_label}'. Expected MOD-1 to MOD-6."

        return result


class RedressalParser(ResponseParser):
    """Parser for Redressal Points domain (JSON array of strings)."""

    MIN_POINTS = 2
    MAX_POINTS = 10

    def parse(self, response_text: str) -> ValidationResult:
        """Parse redressal points response."""
        result = ValidationResult()

        # Extract tag content
        raw_label = self.extract_tag_content(response_text)
        if raw_label is None:
            result.parsing_error = "Could not find << >> tags in response"
            return result

        # Try to parse as JSON
        try:
            points = json.loads(raw_label)

            # Validate structure
            if not isinstance(points, list):
                result.validity_error = f"Redressal points must be a JSON array, got: {type(points).__name__}"
                return result

            if not all(isinstance(p, str) for p in points):
                result.validity_error = "All redressal points must be strings"
                return result

            # Validate count
            if len(points) < self.MIN_POINTS:
                result.validity_error = f"Redressal points must have at least {self.MIN_POINTS} items, got {len(points)}"
                return result

            if len(points) > self.MAX_POINTS:
                result.validity_error = f"Redressal points must have at most {self.MAX_POINTS} items, got {len(points)}"
                return result

            # Validate each point is non-empty
            empty_points = [i for i, p in enumerate(points) if not p.strip()]
            if empty_points:
                result.validity_error = f"Redressal points at indices {empty_points} are empty"
                return result

            # Success - store as JSON string
            result.label = json.dumps(points)

        except json.JSONDecodeError as e:
            result.validity_error = f"Invalid JSON in redressal points: {str(e)}"

        return result


# ═══════════════════════════════════════════════════════════
# PARSER FACTORY
# ═══════════════════════════════════════════════════════════

class ParserFactory:
    """Factory for creating domain-specific parsers."""

    _parsers = {
        'urgency': UrgencyParser,
        'therapeutic': TherapeuticParser,
        'intensity': IntensityParser,
        'adjunct': AdjunctParser,
        'modality': ModalityParser,
        'redressal': RedressalParser
    }

    @classmethod
    def get_parser(cls, domain: str) -> ResponseParser:
        """
        Get parser for a specific domain.

        Args:
            domain: Domain name

        Returns:
            Parser instance

        Raises:
            ValueError: If domain is not recognized
        """
        domain_lower = domain.lower()

        if domain_lower not in cls._parsers:
            raise ValueError(f"Unknown domain: {domain}. Valid domains: {list(cls._parsers.keys())}")

        parser_class = cls._parsers[domain_lower]
        return parser_class()

    @classmethod
    def get_supported_domains(cls) -> List[str]:
        """Get list of supported domain names."""
        return list(cls._parsers.keys())


# ═══════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════════

def validate_response(domain: str, response_text: str) -> ValidationResult:
    """
    Validate response for a specific domain.

    Args:
        domain: Domain name
        response_text: Full response from AI model

    Returns:
        ValidationResult object

    Example:
        >>> result = validate_response('urgency', 'Analysis... <<LEVEL_3>>')
        >>> if result.is_valid:
        ...     print(f"Label: {result.label}")
        ... else:
        ...     print(f"Error: {result.parsing_error or result.validity_error}")
    """
    parser = ParserFactory.get_parser(domain)
    result = parser.parse(response_text)

    if result.is_valid:
        logger.debug(f"Valid {domain} response: {result.label}")
    else:
        error_msg = result.parsing_error or result.validity_error
        logger.warning(f"Invalid {domain} response: {error_msg}")

    return result


# ═══════════════════════════════════════════════════════════
# BATCH VALIDATION
# ═══════════════════════════════════════════════════════════

def validate_responses_batch(domain: str, responses: List[str]) -> List[ValidationResult]:
    """
    Validate multiple responses in batch.

    Args:
        domain: Domain name
        responses: List of response texts

    Returns:
        List of ValidationResult objects
    """
    parser = ParserFactory.get_parser(domain)
    results = [parser.parse(response) for response in responses]

    valid_count = sum(1 for r in results if r.is_valid)
    logger.info(f"Batch validation: {valid_count}/{len(results)} valid responses for {domain}")

    return results


# ═══════════════════════════════════════════════════════════
# STATISTICS
# ═══════════════════════════════════════════════════════════

def get_validation_stats(results: List[ValidationResult]) -> dict:
    """
    Get statistics from validation results.

    Args:
        results: List of ValidationResult objects

    Returns:
        Dictionary with statistics
    """
    total = len(results)
    valid = sum(1 for r in results if r.is_valid)
    parsing_errors = sum(1 for r in results if r.parsing_error)
    validity_errors = sum(1 for r in results if r.validity_error)

    return {
        'total': total,
        'valid': valid,
        'invalid': total - valid,
        'parsing_errors': parsing_errors,
        'validity_errors': validity_errors,
        'success_rate': (valid / total * 100) if total > 0 else 0
    }
