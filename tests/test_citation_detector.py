"""Tests for citation_detector service."""

from unittest.mock import MagicMock, patch

from app.services.citation_detector import detect_citations


class TestDetectCitations:
    """Test the detect_citations function."""

    @patch("app.services.citation_detector.get_chat_model")
    def test_detect_citations_success(self, mock_get_model):
        """Test that detect_citations parses document IDs from LLM response."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "2\n5"
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        documents = [(1, "report.pdf"), (2, "budget.pdf"), (3, "memo.docx"), (5, "policy.pdf")]
        result = detect_citations("This document references budget.pdf and policy.pdf", documents)
        assert result == [2, 5]

    @patch("app.services.citation_detector.get_chat_model")
    def test_detect_citations_filters_invalid_ids(self, mock_get_model):
        """Test that IDs not in the known documents list are filtered out."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "2\n99\n5\n100"
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        documents = [(1, "report.pdf"), (2, "budget.pdf"), (5, "policy.pdf")]
        result = detect_citations("Content referencing documents", documents)
        # Only IDs 2 and 5 are valid
        assert result == [2, 5]

    @patch("app.services.citation_detector.get_chat_model")
    def test_detect_citations_empty_response(self, mock_get_model):
        """Test that empty LLM response returns empty list."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = ""
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        documents = [(1, "report.pdf"), (2, "budget.pdf")]
        result = detect_citations("Content with no citations", documents)
        assert result == []

    @patch("app.services.citation_detector.get_chat_model")
    def test_detect_citations_no_api_key(self, mock_get_model):
        """Test that no API key (model is None) returns empty list."""
        mock_get_model.return_value = None

        documents = [(1, "report.pdf"), (2, "budget.pdf")]
        result = detect_citations("Some content", documents)
        assert result == []

    def test_detect_citations_empty_documents_list(self):
        """Test that empty documents list returns empty list without calling LLM."""
        result = detect_citations("Some content", [])
        assert result == []

    @patch("app.services.citation_detector.get_chat_model")
    def test_detect_citations_handles_id_prefix(self, mock_get_model):
        """Test that 'ID:' prefix is stripped from LLM response lines."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "ID:2\nID:5"
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        documents = [(2, "budget.pdf"), (5, "policy.pdf")]
        result = detect_citations("References budget and policy", documents)
        assert result == [2, 5]

    @patch("app.services.citation_detector.get_chat_model")
    def test_detect_citations_handles_non_numeric_lines(self, mock_get_model):
        """Test that non-numeric lines are skipped."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "2\nnot_a_number\n5\nabc"
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        documents = [(2, "budget.pdf"), (5, "policy.pdf")]
        result = detect_citations("Content", documents)
        assert result == [2, 5]

    @patch("app.services.citation_detector.get_chat_model")
    def test_detect_citations_llm_exception_returns_empty(self, mock_get_model):
        """Test that LLM exception returns empty list via circuit breaker fallback."""
        mock_model = MagicMock()
        mock_model.invoke.side_effect = Exception("LLM API error")
        mock_get_model.return_value = mock_model

        documents = [(1, "report.pdf"), (2, "budget.pdf")]
        result = detect_citations("Content", documents)
        assert result == []
