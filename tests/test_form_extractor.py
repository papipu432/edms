"""Tests for form_extractor service."""

from unittest.mock import MagicMock, patch

from app.services.form_extractor import extract_fields


class TestExtractFields:
    """Test the extract_fields function."""

    @patch("app.services.form_extractor.get_chat_model")
    def test_extract_fields_success(self, mock_get_model):
        """Test that extract_fields parses JSON LLM response correctly."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = '{"invoice_number": "INV-001", "date": "2024-01-15", "amount": "$5000"}'
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        result = extract_fields("Invoice INV-001 dated 2024-01-15 for $5000")
        assert result == {
            "invoice_number": "INV-001",
            "date": "2024-01-15",
            "amount": "$5000",
        }

    @patch("app.services.form_extractor.get_chat_model")
    def test_extract_fields_no_api_key(self, mock_get_model):
        """Test that no API key (model is None) returns empty dict."""
        mock_get_model.return_value = None

        result = extract_fields("Some document content.")
        assert result == {}

    @patch("app.services.form_extractor.get_chat_model")
    def test_extract_fields_invalid_json_returns_empty(self, mock_get_model):
        """Test that invalid JSON response returns empty dict via fallback."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "This is not valid JSON at all"
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        result = extract_fields("Some document content.")
        assert result == {}

    @patch("app.services.form_extractor.get_chat_model")
    def test_extract_fields_with_custom_prompt(self, mock_get_model):
        """Test that custom extraction_prompt is passed to LLM."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = '{"name": "John Doe", "email": "john@example.com"}'
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        custom_prompt = "Extract contact information as JSON."
        result = extract_fields("Contact: John Doe, john@example.com", extraction_prompt=custom_prompt)

        assert result == {"name": "John Doe", "email": "john@example.com"}
        # Verify custom prompt was used in the system message
        call_args = mock_model.invoke.call_args[0][0]
        system_msg = call_args[0]
        assert custom_prompt in system_msg.content

    @patch("app.services.form_extractor.get_chat_model")
    def test_extract_fields_strips_code_fences(self, mock_get_model):
        """Test that markdown code fences are stripped from response."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = '```json\n{"key": "value"}\n```'
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        result = extract_fields("Document content.")
        assert result == {"key": "value"}

    @patch("app.services.form_extractor.get_chat_model")
    def test_extract_fields_non_dict_returns_empty(self, mock_get_model):
        """Test that non-dict JSON response returns empty dict."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = '["item1", "item2"]'
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        result = extract_fields("Document content.")
        assert result == {}

    @patch("app.services.form_extractor.get_chat_model")
    def test_extract_fields_llm_exception_returns_empty(self, mock_get_model):
        """Test that LLM exception returns empty dict via circuit breaker fallback."""
        mock_model = MagicMock()
        mock_model.invoke.side_effect = Exception("LLM API error")
        mock_get_model.return_value = mock_model

        result = extract_fields("Some content.")
        assert result == {}
