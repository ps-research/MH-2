"""
Tests for response validation utilities.
"""
import pytest
from src.utils.validators import (
    UrgencyParser,
    TherapeuticParser,
    IntensityParser,
    AdjunctParser,
    ModalityParser,
    RedressalParser,
    ParserFactory,
    validate_response,
    ValidationResult
)


class TestUrgencyParser:
    """Tests for UrgencyParser."""

    def test_valid_urgency_level_0(self):
        response = "Analysis here... <<LEVEL_0>>"
        parser = UrgencyParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "LEVEL_0"
        assert result.parsing_error is None
        assert result.validity_error is None

    def test_valid_urgency_level_4(self):
        response = "Critical case... <<LEVEL_4>>"
        parser = UrgencyParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "LEVEL_4"

    def test_urgency_with_space(self):
        response = "Analysis... <<LEVEL 3>>"
        parser = UrgencyParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "LEVEL_3"

    def test_urgency_lowercase(self):
        response = "Analysis... <<level_2>>"
        parser = UrgencyParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "LEVEL_2"

    def test_missing_tags(self):
        response = "No tags here LEVEL_3"
        parser = UrgencyParser()
        result = parser.parse(response)

        assert not result.is_valid
        assert result.parsing_error == "Could not find << >> tags in response"

    def test_invalid_level(self):
        response = "Analysis... <<LEVEL_5>>"
        parser = UrgencyParser()
        result = parser.parse(response)

        assert not result.is_valid
        assert result.validity_error is not None


class TestTherapeuticParser:
    """Tests for TherapeuticParser."""

    def test_single_therapy(self):
        response = "Analysis... <<TA-1>>"
        parser = TherapeuticParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "TA-1"

    def test_multiple_therapies(self):
        response = "Analysis... <<TA-1, TA-3, TA-7>>"
        parser = TherapeuticParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "TA-1, TA-3, TA-7"

    def test_duplicate_removal(self):
        response = "Analysis... <<TA-1, TA-1, TA-3>>"
        parser = TherapeuticParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "TA-1, TA-3"

    def test_all_therapies(self):
        response = "<<TA-1, TA-2, TA-3, TA-4, TA-5, TA-6, TA-7, TA-8, TA-9>>"
        parser = TherapeuticParser()
        result = parser.parse(response)

        assert result.is_valid
        assert "TA-1" in result.label
        assert "TA-9" in result.label

    def test_no_valid_codes(self):
        response = "Analysis... <<NONE>>"
        parser = TherapeuticParser()
        result = parser.parse(response)

        assert not result.is_valid
        assert result.validity_error is not None


class TestIntensityParser:
    """Tests for IntensityParser."""

    def test_valid_intensity_levels(self):
        parser = IntensityParser()

        for level in range(1, 6):
            response = f"Analysis... <<INT-{level}>>"
            result = parser.parse(response)

            assert result.is_valid
            assert result.label == f"INT-{level}"

    def test_invalid_intensity(self):
        response = "Analysis... <<INT-6>>"
        parser = IntensityParser()
        result = parser.parse(response)

        assert not result.is_valid
        assert result.validity_error is not None


class TestAdjunctParser:
    """Tests for AdjunctParser."""

    def test_single_adjunct(self):
        response = "Analysis... <<ADJ-1>>"
        parser = AdjunctParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "ADJ-1"

    def test_multiple_adjuncts(self):
        response = "Analysis... <<ADJ-1, ADJ-3, ADJ-5>>"
        parser = AdjunctParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "ADJ-1, ADJ-3, ADJ-5"

    def test_none_adjunct(self):
        response = "Analysis... <<NONE>>"
        parser = AdjunctParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "NONE"

    def test_none_case_insensitive(self):
        response = "Analysis... <<none>>"
        parser = AdjunctParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "NONE"


class TestModalityParser:
    """Tests for ModalityParser."""

    def test_single_modality(self):
        response = "Analysis... <<MOD-1>>"
        parser = ModalityParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "MOD-1"

    def test_multiple_modalities(self):
        response = "Analysis... <<MOD-1, MOD-2, MOD-5>>"
        parser = ModalityParser()
        result = parser.parse(response)

        assert result.is_valid
        assert result.label == "MOD-1, MOD-2, MOD-5"


class TestRedressalParser:
    """Tests for RedressalParser."""

    def test_valid_redressal_points(self):
        response = '''Analysis... <<["Depression from breakup", "Academic decline", "Poor sleep"]>>'''
        parser = RedressalParser()
        result = parser.parse(response)

        assert result.is_valid
        assert "Depression from breakup" in result.label

    def test_minimum_points(self):
        response = '''<<["Point 1", "Point 2"]>>'''
        parser = RedressalParser()
        result = parser.parse(response)

        assert result.is_valid

    def test_too_few_points(self):
        response = '''<<["Only one point"]>>'''
        parser = RedressalParser()
        result = parser.parse(response)

        assert not result.is_valid
        assert "at least 2" in result.validity_error.lower()

    def test_invalid_json(self):
        response = '''<<["Point 1", "Point 2">>'''  # Missing closing bracket
        parser = RedressalParser()
        result = parser.parse(response)

        assert not result.is_valid
        assert "JSON" in result.validity_error

    def test_not_array(self):
        response = '''<<{"key": "value"}>>'''
        parser = RedressalParser()
        result = parser.parse(response)

        assert not result.is_valid
        assert "array" in result.validity_error.lower()


class TestParserFactory:
    """Tests for ParserFactory."""

    def test_get_urgency_parser(self):
        parser = ParserFactory.get_parser('urgency')
        assert isinstance(parser, UrgencyParser)

    def test_get_therapeutic_parser(self):
        parser = ParserFactory.get_parser('therapeutic')
        assert isinstance(parser, TherapeuticParser)

    def test_case_insensitive(self):
        parser = ParserFactory.get_parser('URGENCY')
        assert isinstance(parser, UrgencyParser)

    def test_invalid_domain(self):
        with pytest.raises(ValueError, match="Unknown domain"):
            ParserFactory.get_parser('invalid_domain')

    def test_get_supported_domains(self):
        domains = ParserFactory.get_supported_domains()
        assert len(domains) == 6
        assert 'urgency' in domains
        assert 'redressal' in domains


class TestValidateResponse:
    """Tests for validate_response convenience function."""

    def test_validate_urgency(self):
        response = "<<LEVEL_2>>"
        result = validate_response('urgency', response)

        assert result.is_valid
        assert result.label == "LEVEL_2"

    def test_validate_therapeutic(self):
        response = "<<TA-1, TA-7>>"
        result = validate_response('therapeutic', response)

        assert result.is_valid
        assert "TA-1" in result.label

    def test_validate_invalid(self):
        response = "No tags here"
        result = validate_response('urgency', response)

        assert not result.is_valid
        assert result.parsing_error is not None
