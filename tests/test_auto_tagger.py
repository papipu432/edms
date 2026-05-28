"""Tests for auto_tagger service."""

from unittest.mock import MagicMock, patch

from app.services.auto_tagger import generate_tags


class TestGenerateTags:
    """Test the generate_tags function."""

    @patch("app.services.auto_tagger.get_chat_model")
    def test_generate_tags_success(self, mock_get_model):
        """Test that generate_tags parses LLM response correctly."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "finance\nbudget\nquarterly\nreport"
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        tags = generate_tags("Some document content about quarterly finance budget report.")
        assert tags == ["finance", "budget", "quarterly", "report"]

    @patch("app.services.auto_tagger.get_chat_model")
    def test_generate_tags_empty_response(self, mock_get_model):
        """Test that empty LLM response returns empty list."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = ""
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        tags = generate_tags("Some document content.")
        assert tags == []

    @patch("app.services.auto_tagger.get_chat_model")
    def test_generate_tags_no_api_key(self, mock_get_model):
        """Test that no API key (model is None) returns empty list."""
        mock_get_model.return_value = None

        tags = generate_tags("Some document content.")
        assert tags == []

    @patch("app.services.auto_tagger.get_chat_model")
    def test_generate_tags_limits_to_five(self, mock_get_model):
        """Test that at most 5 tags are returned."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "tag1\ntag2\ntag3\ntag4\ntag5\ntag6\ntag7"
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        tags = generate_tags("Document with many topics.")
        assert len(tags) == 5

    @patch("app.services.auto_tagger.get_chat_model")
    def test_generate_tags_strips_bullets(self, mock_get_model):
        """Test that bullet markers are stripped from tag names."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "- finance\n* budget\n• quarterly"
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        tags = generate_tags("Content about finance.")
        assert tags == ["finance", "budget", "quarterly"]

    @patch("app.services.auto_tagger.get_chat_model")
    def test_generate_tags_truncates_long_tags(self, mock_get_model):
        """Test that tags exceeding 100 chars are truncated."""
        mock_model = MagicMock()
        long_tag = "a" * 150
        mock_result = MagicMock()
        mock_result.content = long_tag
        mock_model.invoke.return_value = mock_result
        mock_get_model.return_value = mock_model

        tags = generate_tags("Content.")
        assert len(tags[0]) == 100

    @patch("app.services.auto_tagger.get_chat_model")
    def test_generate_tags_llm_exception_returns_empty(self, mock_get_model):
        """Test that LLM exception returns empty list via circuit breaker fallback."""
        mock_model = MagicMock()
        mock_model.invoke.side_effect = Exception("LLM API error")
        mock_get_model.return_value = mock_model

        tags = generate_tags("Some content.")
        assert tags == []
